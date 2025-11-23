"""
OCR Preprocessing Pipeline
Improves OCR accuracy through intelligent image preprocessing.
"""

import cv2
import numpy as np
from PIL import Image
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class OCRPreprocessor:
    """
    Intelligent image preprocessing for OCR accuracy improvement.

    Applies adaptive preprocessing based on document quality analysis.
    """

    def __init__(self):
        self.config = {
            'target_dpi': 300,  # Optimal DPI for Tesseract
            'min_dpi': 150,     # Minimum acceptable DPI
            'denoise_strength': 10,
            'sharpen_strength': 1.5,
        }

    def preprocess(self, image_path: str, analysis: dict) -> np.ndarray:
        """
        Main preprocessing pipeline.

        Args:
            image_path: Path to image file
            analysis: Document analysis from DocumentAnalyzer

        Returns:
            Preprocessed image as numpy array
        """
        logger.info(f"Preprocessing image: {image_path}")

        # Step 1: Load image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Failed to load image: {image_path}")

        # Step 2: Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Step 3: Deskew if needed
        if analysis.get('skew_angle', 0) > 1.0:
            gray = self._deskew(gray, analysis['skew_angle'])
            logger.info(f"Deskewed by {analysis['skew_angle']:.2f} degrees")

        # Step 4: Enhance resolution if low DPI
        if analysis.get('dpi', 300) < self.config['min_dpi']:
            gray = self._upscale(gray, analysis.get('dpi', 150))
            logger.info(f"Upscaled from {analysis.get('dpi')} DPI")

        # Step 5: Denoise if noisy
        if analysis.get('noise_level', 0) > 0.3:
            gray = self._denoise(gray)
            logger.info("Applied denoising")

        # Step 6: Enhance contrast if low
        if analysis.get('contrast', 1.0) < 0.5:
            gray = self._enhance_contrast(gray)
            logger.info("Enhanced contrast")

        # Step 7: Binarization (Otsu's method)
        binary = self._binarize(gray)

        # Step 8: Remove borders/shadows
        binary = self._remove_borders(binary)

        # Step 9: Sharpen text
        sharpened = self._sharpen(binary)

        return sharpened

    def _deskew(self, image: np.ndarray, angle: float) -> np.ndarray:
        """
        Correct image rotation/skew.

        Args:
            image: Input image
            angle: Rotation angle in degrees

        Returns:
            Rotated image
        """
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)

        # Create rotation matrix
        M = cv2.getRotationMatrix2D(center, angle, 1.0)

        # Perform rotation
        rotated = cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        return rotated

    def _upscale(self, image: np.ndarray, current_dpi: int) -> np.ndarray:
        """
        Upscale image to target DPI using bicubic interpolation.

        Args:
            image: Input image
            current_dpi: Current image DPI

        Returns:
            Upscaled image
        """
        scale_factor = self.config['target_dpi'] / current_dpi

        new_width = int(image.shape[1] * scale_factor)
        new_height = int(image.shape[0] * scale_factor)

        upscaled = cv2.resize(
            image,
            (new_width, new_height),
            interpolation=cv2.INTER_CUBIC
        )

        return upscaled

    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """
        Remove noise using Non-local Means Denoising.

        Args:
            image: Input image

        Returns:
            Denoised image
        """
        denoised = cv2.fastNlMeansDenoising(
            image,
            None,
            h=self.config['denoise_strength'],
            templateWindowSize=7,
            searchWindowSize=21
        )

        return denoised

    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).

        Args:
            image: Input image

        Returns:
            Contrast-enhanced image
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(image)

        return enhanced

    def _binarize(self, image: np.ndarray) -> np.ndarray:
        """
        Convert to binary image using Otsu's method.

        Args:
            image: Input grayscale image

        Returns:
            Binary image
        """
        # Apply Gaussian blur before binarization
        blurred = cv2.GaussianBlur(image, (5, 5), 0)

        # Otsu's binarization
        _, binary = cv2.threshold(
            blurred,
            0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        return binary

    def _remove_borders(self, image: np.ndarray) -> np.ndarray:
        """
        Remove black borders and shadows from scanned documents.

        Args:
            image: Input binary image

        Returns:
            Image with borders removed
        """
        # Find contours
        contours, _ = cv2.findContours(
            image,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return image

        # Find largest contour (document boundary)
        largest_contour = max(contours, key=cv2.contourArea)

        # Get bounding box
        x, y, w, h = cv2.boundingRect(largest_contour)

        # Crop to document boundary with small margin
        margin = 10
        cropped = image[
            max(0, y - margin):min(image.shape[0], y + h + margin),
            max(0, x - margin):min(image.shape[1], x + w + margin)
        ]

        return cropped

    def _sharpen(self, image: np.ndarray) -> np.ndarray:
        """
        Sharpen text edges for better OCR.

        Args:
            image: Input image

        Returns:
            Sharpened image
        """
        # Sharpening kernel
        kernel = np.array([
            [-1, -1, -1],
            [-1,  9, -1],
            [-1, -1, -1]
        ]) * self.config['sharpen_strength']

        sharpened = cv2.filter2D(image, -1, kernel)

        return sharpened

    def save_debug_image(self, image: np.ndarray, output_path: str):
        """
        Save preprocessed image for debugging.

        Args:
            image: Preprocessed image
            output_path: Path to save image
        """
        cv2.imwrite(output_path, image)
        logger.debug(f"Saved debug image: {output_path}")
