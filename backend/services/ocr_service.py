"""
OCR Service for extracting text from PDF documents and images.
Uses Tesseract OCR (free) by default, with upgrade path to Google Vision API.

Supports:
- Image files (JPG, PNG, TIFF, BMP, GIF)
- PDFs with embedded text (extraction without OCR)
- Image-based PDFs (scanned documents requiring OCR)
"""
import os
import logging
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import io
from typing import Optional, Dict, Any
import sys
from pathlib import Path
import PyPDF2

sys.path.append(str(Path(__file__).parent.parent))

from config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """
    Service for extracting text from PDF documents using OCR.
    Supports both Tesseract (free) and Google Vision API (paid, higher accuracy).
    """

    def __init__(self):
        """
        Initialize OCR service.
        Uses Tesseract by default, with option to upgrade to Google Vision API later.
        """
        self.use_google = settings.use_google_vision

        if self.use_google:
            try:
                from google.cloud import vision
                self.vision_client = vision.ImageAnnotatorClient()
                logger.info("[OK] Google Vision API initialized")
            except Exception as e:
                logger.warning(f"Google Vision API not available, falling back to Tesseract: {e}")
                self.use_google = False
        else:
            logger.info("[OK] Using Tesseract OCR (free)")

    def is_pdf_text_based(self, pdf_path: str) -> bool:
        """
        Check if a PDF has embedded text or is image-based.

        Args:
            pdf_path: Path to PDF file

        Returns:
            True if PDF has text, False if image-based
        """
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # Check first page for text
                if len(pdf_reader.pages) > 0:
                    first_page = pdf_reader.pages[0]
                    text = first_page.extract_text().strip()

                    # If we extracted meaningful text, it's text-based
                    # Threshold: More than 10 characters
                    if len(text) > 10:
                        logger.info(f"PDF has embedded text ({len(text)} chars)")
                        return True

                logger.info("PDF appears to be image-based (no text extracted)")
                return False

        except Exception as e:
            logger.error(f"Error checking PDF text: {e}")
            # Assume image-based if we can't determine
            return False

    async def extract_text_from_image(self, image_path: str) -> str:
        """
        Extract text from an image file using OCR.

        Args:
            image_path: Path to image file (JPG, PNG, TIFF, etc.)

        Returns:
            Extracted text
        """
        try:
            logger.info(f"Running OCR on image: {image_path}")

            # Open image
            image = Image.open(image_path)

            # Use Google Vision if enabled, otherwise Tesseract
            if self.use_google:
                text = await self._google_ocr(image)
            else:
                text = await self._tesseract_ocr(image)

            logger.info(f"OCR extracted {len(text)} characters from image")
            return text.strip()

        except Exception as e:
            logger.error(f"OCR failed for image {image_path}: {e}")
            return ""

    def extract_text_with_coordinates(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text with bounding box coordinates from image or PDF.
        Returns data suitable for creating a selectable text overlay.

        Args:
            file_path: Path to image or PDF file

        Returns:
            Dictionary with:
                - words: List of word dictionaries with text, x, y, width, height
                - image_width: Width of source image
                - image_height: Height of source image
        """
        try:
            file_ext = Path(file_path).suffix.lower()

            # Handle images
            if file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif']:
                image = Image.open(file_path)
                return self._extract_coordinates_from_image(image)

            # Handle PDFs (first page only for now)
            elif file_ext == '.pdf':
                # ALWAYS convert PDF to image and extract coordinates
                # (We're now running OCR on all PDFs to capture table content)
                images = convert_from_path(file_path, first_page=1, last_page=1, dpi=300)
                if images:
                    return self._extract_coordinates_from_image(images[0])
                else:
                    return {'words': [], 'image_width': 0, 'image_height': 0}

            return {'words': [], 'image_width': 0, 'image_height': 0}

        except Exception as e:
            logger.error(f"Error extracting coordinates from {file_path}: {e}")
            return {'words': [], 'image_width': 0, 'image_height': 0}

    def _extract_coordinates_from_image(self, image: Image.Image) -> Dict[str, Any]:
        """
        Extract text with coordinates from a PIL Image using Tesseract.

        Args:
            image: PIL Image object

        Returns:
            Dictionary with words and bounding boxes
        """
        try:
            # Get OCR data with bounding boxes
            # Output is a dict with keys: level, page_num, block_num, par_num, line_num, word_num,
            # left, top, width, height, conf, text
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, lang='eng')

            words = []
            n_boxes = len(data['text'])

            for i in range(n_boxes):
                # Skip empty text
                if not data['text'][i].strip():
                    continue

                # Skip low confidence (below 30)
                if int(data['conf'][i]) < 30:
                    continue

                word_data = {
                    'text': data['text'][i],
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i],
                    'confidence': int(data['conf'][i])
                }
                words.append(word_data)

            logger.info(f"Extracted {len(words)} words with coordinates")

            return {
                'words': words,
                'image_width': image.width,
                'image_height': image.height
            }

        except Exception as e:
            logger.error(f"Error extracting coordinates from image: {e}")
            return {'words': [], 'image_width': 0, 'image_height': 0}

    def extract_text_from_file(self, file_path: str, max_pages: int = 10) -> Dict[str, Any]:
        """
        Extract text from any supported file (PDF or image).

        Args:
            file_path: Path to file
            max_pages: Maximum number of PDF pages to process

        Returns:
            Dictionary with:
                - text: Extracted text
                - method: 'embedded', 'ocr', or 'image'
                - file_type: 'pdf' or 'image'
        """
        file_path_obj = Path(file_path)
        extension = file_path_obj.suffix.lower()

        try:
            # Handle images
            if extension in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif']:
                logger.info(f"Processing image file: {file_path}")
                image = Image.open(file_path)
                # Use sync version of tesseract for simplicity
                text = pytesseract.image_to_string(image, lang='eng')

                return {
                    'text': text.strip(),
                    'method': 'image_ocr',
                    'file_type': 'image'
                }

            # Handle PDFs
            elif extension == '.pdf':
                # ALWAYS run OCR on PDFs to ensure we capture table content
                # Tables are often images even in "text-based" PDFs
                logger.info(f"Running OCR on PDF to capture all content including tables...")
                # Convert to images and OCR
                images = convert_from_path(
                    file_path,
                    first_page=1,
                    last_page=min(max_pages, 5),  # Limit to 5 pages for speed
                    dpi=300
                )

                all_text = []
                for i, image in enumerate(images):
                    logger.info(f"OCR on PDF page {i + 1}/{len(images)}")
                    page_text = pytesseract.image_to_string(image, lang='eng')
                    all_text.append(page_text)

                text = "\n\n--- Page Break ---\n\n".join(all_text).strip()

                return {
                    'text': text,
                    'method': 'pdf_ocr',
                    'file_type': 'pdf'
                }

            else:
                logger.warning(f"Unsupported file type: {extension}")
                return {
                    'text': '',
                    'method': 'unsupported',
                    'file_type': 'unknown'
                }

        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return {
                'text': '',
                'method': 'error',
                'file_type': 'unknown',
                'error': str(e)
            }

    async def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF using OCR.
        Uses Tesseract by default, Google Vision if enabled in settings.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text from the PDF

        Raises:
            Exception: If OCR processing fails
        """
        try:
            # Convert PDF to images (limit to first 5 pages for MVP to save processing time)
            # Each page becomes a PIL Image object
            images = convert_from_path(
                pdf_path,
                dpi=300,  # Higher DPI = better quality = better OCR accuracy
                first_page=1,
                last_page=5  # Only process first 5 pages for speed
            )

            all_text = []

            # Process each page
            for i, image in enumerate(images):
                if self.use_google:
                    text = await self._google_ocr(image)
                else:
                    text = await self._tesseract_ocr(image)

                if text:
                    all_text.append(text)

            # Combine all pages with double newline separator
            return "\n\n".join(all_text)

        except Exception as e:
            raise Exception(f"OCR processing failed: {str(e)}")

    async def _tesseract_ocr(self, image: Image.Image) -> str:
        """
        Use Tesseract for OCR (free, open source).
        85-90% accuracy - good enough for MVP.

        Args:
            image: PIL Image object

        Returns:
            Extracted text from the image
        """
        try:
            # Optional preprocessing for better OCR results (commented out for simplicity)
            # image = image.convert('L')  # Convert to grayscale
            # image = image.point(lambda x: 0 if x < 128 else 255, '1')  # Binarize

            # Extract text using Tesseract
            text = pytesseract.image_to_string(image, lang='eng')
            return text

        except Exception as e:
            raise Exception(f"Tesseract OCR failed: {str(e)}")

    async def _google_ocr(self, image: Image.Image) -> str:
        """
        Use Google Vision API for OCR (paid, 99% accuracy).
        Enable this once you have paying customers.

        Args:
            image: PIL Image object

        Returns:
            Extracted text from the image
        """
        try:
            from google.cloud import vision

            # Convert PIL Image to bytes for Google Vision API
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            # Create Vision API image object
            vision_image = vision.Image(content=img_byte_arr)

            # Perform text detection
            response = self.vision_client.text_detection(image=vision_image)
            texts = response.text_annotations

            # First annotation contains all text
            if texts:
                return texts[0].description
            return ""

        except Exception as e:
            print(f"Google OCR failed, falling back to Tesseract: {e}")
            return await self._tesseract_ocr(image)

    def validate_ocr_quality(self, text: str) -> bool:
        """
        Basic validation to ensure OCR produced meaningful text.
        Returns False if text is too short or mostly garbage.

        Args:
            text: Extracted text to validate

        Returns:
            True if text quality is acceptable, False otherwise
        """
        # Check minimum length
        if not text or len(text.strip()) < 50:
            return False

        # Check for reasonable word count
        words = text.split()
        if len(words) < 10:
            return False

        # Check that text isn't mostly special characters
        # Should be at least 60% alphanumeric/spaces
        alphanumeric_ratio = sum(c.isalnum() or c.isspace() for c in text) / len(text)
        if alphanumeric_ratio < 0.6:
            return False

        return True


# Global instance
_ocr_service = None


def get_ocr_service() -> OCRService:
    """Get or create the global OCR service instance."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
