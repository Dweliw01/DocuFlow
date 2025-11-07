"""
OCR Service for extracting text from PDF documents.
Uses Tesseract OCR (free) by default, with upgrade path to Google Vision API.
"""
import os
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import io
from typing import Optional
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import settings


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
                print("✓ Google Vision API initialized")
            except Exception as e:
                print(f"⚠ Google Vision API not available, falling back to Tesseract: {e}")
                self.use_google = False
        else:
            print("✓ Using Tesseract OCR (free)")

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
