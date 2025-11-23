"""
Document Quality Analysis
Analyzes document images to determine optimal preprocessing strategy.
"""

import cv2
import numpy as np
from PIL import Image
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class DocumentAnalyzer:
    """
    Analyzes document images to determine quality metrics.

    Provides information needed for adaptive preprocessing.
    """

    def analyze(self, image_path: str) -> Dict:
        """
        Analyze document image quality.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with analysis results:
            {
                'dpi': int,
                'skew_angle': float,
                'noise_level': float,
                'contrast': float,
                'is_handwritten': bool,
                'quality_score': float
            }
        """
        logger.info(f"Analyzing document: {image_path}")

        # Load image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Failed to load image: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Analyze various quality metrics
        analysis = {
            'dpi': self._estimate_dpi(image_path, gray),
            'skew_angle': self._detect_skew(gray),
            'noise_level': self._measure_noise(gray),
            'contrast': self._measure_contrast(gray),
            'is_handwritten': self._detect_handwriting(gray),
            'quality_score': 0.0  # Will be calculated
        }

        # Calculate overall quality score (0-1)
        analysis['quality_score'] = self._calculate_quality_score(analysis)

        logger.info(f"Analysis complete: {analysis}")
        return analysis

    def _estimate_dpi(self, image_path: str, image: np.ndarray) -> int:
        """
        Estimate image DPI.

        Args:
            image_path: Path to image file
            image: Image array

        Returns:
            Estimated DPI
        """
        try:
            # Try to get DPI from image metadata
            with Image.open(image_path) as pil_img:
                dpi = pil_img.info.get('dpi')
                if dpi:
                    return int(dpi[0]) if isinstance(dpi, tuple) else int(dpi)
        except Exception as e:
            logger.warning(f"Could not read DPI from metadata: {e}")

        # Fallback: estimate based on image size
        # Assume standard letter size (8.5" x 11")
        height_inches = 11
        estimated_dpi = image.shape[0] / height_inches

        return int(estimated_dpi)

    def _detect_skew(self, image: np.ndarray) -> float:
        """
        Detect document skew angle using Hough Line Transform.

        Args:
            image: Grayscale image

        Returns:
            Skew angle in degrees
        """
        # Edge detection
        edges = cv2.Canny(image, 50, 150, apertureSize=3)

        # Detect lines
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)

        if lines is None:
            return 0.0

        # Calculate angles
        angles = []
        for rho, theta in lines[:, 0]:
            angle = np.degrees(theta) - 90
            if -45 < angle < 45:
                angles.append(angle)

        if not angles:
            return 0.0

        # Return median angle
        median_angle = np.median(angles)
        return float(median_angle)

    def _measure_noise(self, image: np.ndarray) -> float:
        """
        Measure noise level using Laplacian variance.

        Args:
            image: Grayscale image

        Returns:
            Noise level (0-1, higher = more noise)
        """
        # Calculate Laplacian variance
        laplacian = cv2.Laplacian(image, cv2.CV_64F)
        variance = laplacian.var()

        # Normalize to 0-1 (empirical thresholds)
        # Clean images: variance > 500
        # Noisy images: variance < 100
        noise_level = 1.0 - min(variance / 500, 1.0)

        return float(noise_level)

    def _measure_contrast(self, image: np.ndarray) -> float:
        """
        Measure image contrast using standard deviation.

        Args:
            image: Grayscale image

        Returns:
            Contrast level (0-1, higher = better contrast)
        """
        # Calculate standard deviation
        std_dev = np.std(image)

        # Normalize to 0-1
        # Good contrast: std_dev > 50
        # Low contrast: std_dev < 20
        contrast = min(std_dev / 50, 1.0)

        return float(contrast)

    def _detect_handwriting(self, image: np.ndarray) -> bool:
        """
        Detect if document contains handwriting.

        Args:
            image: Grayscale image

        Returns:
            True if handwriting detected
        """
        # This is a simplified heuristic
        # For production, consider ML-based detection

        # Calculate edge density
        edges = cv2.Canny(image, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # Handwritten documents typically have:
        # - Higher edge density (more irregular strokes)
        # - Lower contrast
        # - More variation in line thickness

        # Heuristic threshold
        is_handwritten = edge_density > 0.15

        return bool(is_handwritten)

    def _calculate_quality_score(self, analysis: Dict) -> float:
        """
        Calculate overall quality score.

        Args:
            analysis: Analysis dictionary

        Returns:
            Quality score (0-1, higher = better quality)
        """
        # Weighted scoring
        dpi_score = min(analysis['dpi'] / 300, 1.0)  # 300 DPI = perfect
        skew_score = 1.0 - min(abs(analysis['skew_angle']) / 10, 1.0)  # 0° = perfect
        noise_score = 1.0 - analysis['noise_level']  # Less noise = better
        contrast_score = analysis['contrast']  # Higher contrast = better

        # Calculate weighted average
        quality_score = (
            dpi_score * 0.3 +
            skew_score * 0.2 +
            noise_score * 0.3 +
            contrast_score * 0.2
        )

        return float(quality_score)
