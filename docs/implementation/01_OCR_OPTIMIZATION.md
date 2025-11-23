# 01 - OCR Optimization Implementation Guide

**Status:** 🔴 Not Started
**Priority:** 🔴 HIGH (Start here)
**Timeline:** Week 1-2
**Dependencies:** None
**Estimated Time:** 1-2 weeks

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Objectives](#objectives)
3. [Prerequisites](#prerequisites)
4. [Implementation Steps](#implementation-steps)
   - [Step 1: Install Dependencies](#step-1-install-dependencies)
   - [Step 2: Create OCR Preprocessor](#step-2-create-ocr-preprocessor)
   - [Step 3: Create Document Analyzer](#step-3-create-document-analyzer)
   - [Step 4: Update OCR Service](#step-4-update-ocr-service)
   - [Step 5: Create Test Dataset](#step-5-create-test-dataset)
   - [Step 6: Build Accuracy Benchmark](#step-6-build-accuracy-benchmark)
5. [Testing Checklist](#testing-checklist)
6. [Integration Verification](#integration-verification)
7. [Success Criteria](#success-criteria)
8. [Troubleshooting](#troubleshooting)
9. [Next Steps](#next-steps)

---

## Overview

Currently, DocuFlow uses basic Tesseract OCR with 85-90% accuracy. This is acceptable for clean documents but struggles with:
- Scanned documents with skew/rotation
- Low contrast or faded text
- Noisy backgrounds
- Mixed quality documents

**The Solution:** Implement intelligent image preprocessing before OCR to improve accuracy from **85% → 92-95%** on printed documents and **80% → 88%+** on scanned documents.

This guide will walk you through creating:
1. **OCRPreprocessor** - Intelligent image preprocessing pipeline
2. **DocumentAnalyzer** - Analyzes document quality and type
3. **Enhanced OCRService** - Integrates preprocessing with existing OCR
4. **Benchmark Suite** - Measures accuracy improvements

---

## Objectives

**Primary Goal:** Improve OCR accuracy to 92%+ on clean printed documents

**Secondary Goals:**
- Improve scanned document accuracy to 88%+
- Maintain processing speed (< 5 seconds per page)
- No regression on existing functionality
- All tests passing (unit + integration)

**Success Metrics:**
- ✅ Clean printed docs: 92%+ character accuracy
- ✅ Scanned docs: 88%+ character accuracy
- ✅ Processing time: < 5 seconds per page
- ✅ All unit tests passing (4/4 new tests)
- ✅ Integration tests passing
- ✅ No breaking changes to API

---

## Prerequisites

### System Requirements
- Python 3.11+
- Tesseract OCR 5.x installed
- 4GB+ RAM available
- Storage for test dataset (500MB+)

### Python Packages
```bash
pip install opencv-python==4.8.1.78
pip install opencv-contrib-python==4.8.1.78
pip install numpy==1.24.3
pip install Pillow==10.1.0
pip install pytesseract==0.3.10
```

### Verify Tesseract Installation
```bash
# Check version
tesseract --version

# Should output:
# tesseract 5.x.x
```

---

## Implementation Steps

### Step 1: Install Dependencies

**1.1 Install OpenCV**

For Windows:
```bash
pip install opencv-python opencv-contrib-python
```

For Linux/Mac:
```bash
pip install opencv-python opencv-contrib-python
sudo apt-get install libgl1-mesa-glx  # Ubuntu/Debian
```

**1.2 Verify Installation**

Create a test script `test_opencv.py`:
```python
import cv2
import numpy as np

print(f"OpenCV version: {cv2.__version__}")

# Test basic image operations
img = np.zeros((100, 100, 3), dtype=np.uint8)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
print("✓ OpenCV working correctly")
```

Run it:
```bash
python test_opencv.py
```

Expected output:
```
OpenCV version: 4.8.1
✓ OpenCV working correctly
```

**1.3 Update requirements.txt**

Add to `backend/requirements.txt`:
```txt
opencv-python==4.8.1.78
opencv-contrib-python==4.8.1.78
numpy==1.24.3
```

---

### Step 2: Create OCR Preprocessor

**2.1 Create Directory Structure**

```bash
mkdir -p backend/services/ocr
touch backend/services/ocr/__init__.py
touch backend/services/ocr/preprocessor.py
touch backend/services/ocr/analyzer.py
```

**2.2 Create `backend/services/ocr/preprocessor.py`**

```python
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
```

---

### Step 3: Create Document Analyzer

**3.1 Create `backend/services/ocr/analyzer.py`**

```python
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
```

---

### Step 4: Update OCR Service

**4.1 Update `backend/services/ocr_service.py`**

Add imports and integrate preprocessing:

```python
# Add to imports at top of file
from backend.services.ocr.preprocessor import OCRPreprocessor
from backend.services.ocr.analyzer import DocumentAnalyzer
import tempfile
import os

class OCRService:
    def __init__(self):
        self.tesseract_config = r'--oem 3 --psm 3'
        self.preprocessor = OCRPreprocessor()
        self.analyzer = DocumentAnalyzer()

    def extract_text(self, image_path: str, use_preprocessing: bool = True) -> Dict[str, any]:
        """
        Extract text from image using OCR with intelligent preprocessing.

        Args:
            image_path: Path to image file
            use_preprocessing: Whether to apply preprocessing (default: True)

        Returns:
            Dictionary with extracted text and metadata:
            {
                'text': str,
                'confidence': float,
                'preprocessing_applied': bool,
                'quality_score': float
            }
        """
        start_time = time.time()

        try:
            # Step 1: Analyze document
            analysis = self.analyzer.analyze(image_path)
            logger.info(f"Document analysis: quality={analysis['quality_score']:.2f}, "
                       f"dpi={analysis['dpi']}, skew={analysis['skew_angle']:.2f}°")

            # Step 2: Decide if preprocessing is needed
            needs_preprocessing = (
                use_preprocessing and
                (analysis['quality_score'] < 0.8 or analysis['skew_angle'] > 1.0)
            )

            # Step 3: Preprocess if needed
            if needs_preprocessing:
                logger.info("Applying preprocessing...")
                preprocessed_image = self.preprocessor.preprocess(image_path, analysis)

                # Save preprocessed image to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    tmp_path = tmp.name
                    cv2.imwrite(tmp_path, preprocessed_image)

                ocr_image_path = tmp_path
            else:
                logger.info("Skipping preprocessing (high quality document)")
                ocr_image_path = image_path

            # Step 4: Run Tesseract OCR
            try:
                text = pytesseract.image_to_string(
                    Image.open(ocr_image_path),
                    config=self.tesseract_config
                )

                # Get confidence score
                data = pytesseract.image_to_data(
                    Image.open(ocr_image_path),
                    output_type=pytesseract.Output.DICT
                )

                # Calculate average confidence
                confidences = [int(conf) for conf in data['conf'] if conf != '-1']
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            finally:
                # Clean up temp file
                if needs_preprocessing and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            processing_time = time.time() - start_time

            logger.info(f"OCR completed in {processing_time:.2f}s, "
                       f"confidence={avg_confidence:.1f}%, "
                       f"text_length={len(text)}")

            return {
                'text': text.strip(),
                'confidence': avg_confidence / 100,  # Convert to 0-1 scale
                'preprocessing_applied': needs_preprocessing,
                'quality_score': analysis['quality_score'],
                'processing_time': processing_time
            }

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}", exc_info=True)
            raise
```

---

### Step 5: Create Test Dataset

**5.1 Create Test Dataset Directory**

```bash
mkdir -p backend/tests/test_data/ocr
mkdir -p backend/tests/test_data/ocr/clean
mkdir -p backend/tests/test_data/ocr/scanned
mkdir -p backend/tests/test_data/ocr/ground_truth
```

**5.2 Prepare Test Documents**

You'll need to create/collect test documents:

**Clean Printed Documents (20+ files):**
- Invoices from different companies
- Contracts with various layouts
- Forms with tables
- Business letters
- Technical documents

**Scanned Documents (20+ files):**
- Photocopied documents
- Faxed documents
- Photos of documents
- Low-quality scans
- Skewed/rotated scans

**5.3 Create Ground Truth Files**

For each test document, create a `.txt` file with the exact text content:

```
backend/tests/test_data/ocr/
├── clean/
│   ├── invoice_001.pdf
│   ├── invoice_002.pdf
│   └── ...
├── scanned/
│   ├── scanned_001.jpg
│   ├── scanned_002.jpg
│   └── ...
└── ground_truth/
    ├── invoice_001.txt
    ├── invoice_002.txt
    ├── scanned_001.txt
    └── ...
```

**5.4 Helper Script to Create Ground Truth**

Create `backend/scripts/create_ground_truth.py`:

```python
"""
Helper script to create ground truth text files for OCR testing.
"""

import os
from pathlib import Path

def create_ground_truth(image_path: str, text: str):
    """
    Create ground truth text file for an image.

    Args:
        image_path: Path to image file
        text: Ground truth text content
    """
    # Get filename without extension
    filename = Path(image_path).stem

    # Create ground truth file
    gt_path = f"backend/tests/test_data/ocr/ground_truth/{filename}.txt"

    with open(gt_path, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f"✓ Created ground truth: {gt_path}")


if __name__ == "__main__":
    # Example usage
    create_ground_truth(
        "backend/tests/test_data/ocr/clean/invoice_001.pdf",
        "INVOICE\nCompany Name: Acme Corp\nAmount: $1,234.56\n..."
    )
```

---

### Step 6: Build Accuracy Benchmark

**6.1 Create `backend/scripts/benchmark_ocr.py`**

```python
"""
OCR Accuracy Benchmark Script

Measures OCR accuracy improvements by comparing against ground truth.
"""

import os
import sys
from pathlib import Path
import cv2
import numpy as np
from typing import Dict, List, Tuple
import json
from datetime import datetime
import difflib

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ocr_service import OCRService
from services.ocr.analyzer import DocumentAnalyzer


class OCRBenchmark:
    """
    Benchmark OCR accuracy against ground truth dataset.
    """

    def __init__(self):
        self.ocr_service = OCRService()
        self.test_data_dir = Path("backend/tests/test_data/ocr")
        self.results = []

    def run_benchmark(self, use_preprocessing: bool = True) -> Dict:
        """
        Run complete benchmark suite.

        Args:
            use_preprocessing: Test with or without preprocessing

        Returns:
            Benchmark results dictionary
        """
        print(f"\n{'='*60}")
        print(f"OCR Accuracy Benchmark")
        print(f"Preprocessing: {'ENABLED' if use_preprocessing else 'DISABLED'}")
        print(f"{'='*60}\n")

        # Test clean documents
        clean_results = self._test_directory(
            self.test_data_dir / "clean",
            "Clean Printed Documents",
            use_preprocessing
        )

        # Test scanned documents
        scanned_results = self._test_directory(
            self.test_data_dir / "scanned",
            "Scanned Documents",
            use_preprocessing
        )

        # Calculate overall results
        all_results = clean_results + scanned_results

        overall_accuracy = np.mean([r['accuracy'] for r in all_results])
        overall_confidence = np.mean([r['confidence'] for r in all_results])
        avg_processing_time = np.mean([r['processing_time'] for r in all_results])

        # Create summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'preprocessing_enabled': use_preprocessing,
            'total_documents': len(all_results),
            'overall_accuracy': overall_accuracy,
            'overall_confidence': overall_confidence,
            'avg_processing_time': avg_processing_time,
            'clean_docs': {
                'count': len(clean_results),
                'accuracy': np.mean([r['accuracy'] for r in clean_results]),
                'confidence': np.mean([r['confidence'] for r in clean_results])
            },
            'scanned_docs': {
                'count': len(scanned_results),
                'accuracy': np.mean([r['accuracy'] for r in scanned_results]),
                'confidence': np.mean([r['confidence'] for r in scanned_results])
            },
            'results': all_results
        }

        self._print_summary(summary)
        self._save_results(summary)

        return summary

    def _test_directory(self, dir_path: Path, label: str, use_preprocessing: bool) -> List[Dict]:
        """
        Test all documents in a directory.

        Args:
            dir_path: Directory containing test images
            label: Label for this test set
            use_preprocessing: Whether to use preprocessing

        Returns:
            List of test results
        """
        print(f"\n{label}")
        print(f"{'-'*60}")

        results = []

        # Get all image files
        image_files = list(dir_path.glob("*.jpg")) + list(dir_path.glob("*.png")) + list(dir_path.glob("*.pdf"))

        for image_path in sorted(image_files):
            # Get ground truth
            gt_path = self.test_data_dir / "ground_truth" / f"{image_path.stem}.txt"

            if not gt_path.exists():
                print(f"⚠️  Skipping {image_path.name} (no ground truth)")
                continue

            with open(gt_path, 'r', encoding='utf-8') as f:
                ground_truth = f.read().strip()

            # Run OCR
            try:
                ocr_result = self.ocr_service.extract_text(
                    str(image_path),
                    use_preprocessing=use_preprocessing
                )

                extracted_text = ocr_result['text']

                # Calculate accuracy
                accuracy = self._calculate_accuracy(ground_truth, extracted_text)

                result = {
                    'filename': image_path.name,
                    'accuracy': accuracy,
                    'confidence': ocr_result['confidence'],
                    'processing_time': ocr_result['processing_time'],
                    'preprocessing_applied': ocr_result['preprocessing_applied'],
                    'quality_score': ocr_result['quality_score']
                }

                results.append(result)

                # Print result
                status = "✓" if accuracy >= 0.92 else "✗"
                print(f"{status} {image_path.name:30s} "
                      f"Accuracy: {accuracy*100:5.1f}%  "
                      f"Confidence: {ocr_result['confidence']*100:5.1f}%  "
                      f"Time: {ocr_result['processing_time']:.2f}s")

            except Exception as e:
                print(f"✗ {image_path.name:30s} ERROR: {e}")

        return results

    def _calculate_accuracy(self, ground_truth: str, extracted_text: str) -> float:
        """
        Calculate character-level accuracy using edit distance.

        Args:
            ground_truth: Expected text
            extracted_text: OCR extracted text

        Returns:
            Accuracy score (0-1)
        """
        # Normalize text (lowercase, strip whitespace)
        gt_normalized = ground_truth.lower().strip()
        ex_normalized = extracted_text.lower().strip()

        # Calculate similarity using SequenceMatcher
        similarity = difflib.SequenceMatcher(None, gt_normalized, ex_normalized).ratio()

        return similarity

    def _print_summary(self, summary: Dict):
        """Print benchmark summary."""
        print(f"\n{'='*60}")
        print(f"BENCHMARK SUMMARY")
        print(f"{'='*60}")
        print(f"Total Documents:        {summary['total_documents']}")
        print(f"Overall Accuracy:       {summary['overall_accuracy']*100:.2f}%")
        print(f"Overall Confidence:     {summary['overall_confidence']*100:.2f}%")
        print(f"Avg Processing Time:    {summary['avg_processing_time']:.2f}s")
        print(f"\nClean Documents:        {summary['clean_docs']['accuracy']*100:.2f}% "
              f"({summary['clean_docs']['count']} files)")
        print(f"Scanned Documents:      {summary['scanned_docs']['accuracy']*100:.2f}% "
              f"({summary['scanned_docs']['count']} files)")
        print(f"{'='*60}\n")

    def _save_results(self, summary: Dict):
        """Save results to JSON file."""
        output_dir = Path("backend/tests/benchmark_results")
        output_dir.mkdir(exist_ok=True)

        filename = f"ocr_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path = output_dir / filename

        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"✓ Results saved to: {output_path}")


def main():
    """Run benchmark with and without preprocessing for comparison."""
    benchmark = OCRBenchmark()

    # Test WITHOUT preprocessing (baseline)
    print("\n" + "="*60)
    print("BASELINE TEST (No Preprocessing)")
    print("="*60)
    baseline_results = benchmark.run_benchmark(use_preprocessing=False)

    # Test WITH preprocessing
    print("\n" + "="*60)
    print("OPTIMIZED TEST (With Preprocessing)")
    print("="*60)
    optimized_results = benchmark.run_benchmark(use_preprocessing=True)

    # Compare results
    print("\n" + "="*60)
    print("IMPROVEMENT COMPARISON")
    print("="*60)

    baseline_acc = baseline_results['overall_accuracy']
    optimized_acc = optimized_results['overall_accuracy']
    improvement = (optimized_acc - baseline_acc) * 100

    print(f"Baseline Accuracy:      {baseline_acc*100:.2f}%")
    print(f"Optimized Accuracy:     {optimized_acc*100:.2f}%")
    print(f"Improvement:            +{improvement:.2f}%")
    print(f"\n{'SUCCESS!' if optimized_acc >= 0.92 else 'NEEDS WORK'}: "
          f"Target is 92%+ accuracy on clean documents")
    print("="*60)


if __name__ == "__main__":
    main()
```

**6.2 Run Benchmark**

```bash
cd backend
python scripts/benchmark_ocr.py
```

Expected output:
```
============================================================
OCR Accuracy Benchmark
Preprocessing: ENABLED
============================================================

Clean Printed Documents
------------------------------------------------------------
✓ invoice_001.pdf              Accuracy:  94.2%  Confidence:  89.5%  Time: 2.34s
✓ invoice_002.pdf              Accuracy:  95.8%  Confidence:  91.2%  Time: 1.98s
...

Scanned Documents
------------------------------------------------------------
✓ scanned_001.jpg              Accuracy:  88.7%  Confidence:  82.3%  Time: 3.12s
✓ scanned_002.jpg              Accuracy:  89.4%  Confidence:  84.1%  Time: 2.87s
...

============================================================
BENCHMARK SUMMARY
============================================================
Total Documents:        42
Overall Accuracy:       92.34%
Overall Confidence:     86.78%
Avg Processing Time:    2.45s

Clean Documents:        93.67% (21 files)
Scanned Documents:      89.12% (21 files)
============================================================

✓ Results saved to: backend/tests/benchmark_results/ocr_benchmark_20250122_143256.json
```

---

## Testing Checklist

### Unit Tests

**Create `backend/tests/test_ocr_preprocessor.py`:**

```python
import pytest
import cv2
import numpy as np
from backend.services.ocr.preprocessor import OCRPreprocessor
from backend.services.ocr.analyzer import DocumentAnalyzer


class TestOCRPreprocessor:
    """Unit tests for OCR preprocessing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.preprocessor = OCRPreprocessor()
        self.analyzer = DocumentAnalyzer()

    def test_deskew(self):
        """Test image deskewing."""
        # Create skewed test image
        img = np.zeros((500, 500), dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (400, 400), 255, -1)

        # Rotate 5 degrees
        center = (250, 250)
        M = cv2.getRotationMatrix2D(center, 5, 1.0)
        skewed = cv2.warpAffine(img, M, (500, 500))

        # Deskew
        deskewed = self.preprocessor._deskew(skewed, -5)

        # Check that deskewed is closer to original than skewed
        diff_original = np.sum(np.abs(img - deskewed))
        diff_skewed = np.sum(np.abs(img - skewed))

        assert diff_original < diff_skewed

    def test_upscale(self):
        """Test image upscaling."""
        img = np.zeros((100, 100), dtype=np.uint8)

        upscaled = self.preprocessor._upscale(img, current_dpi=150)

        # Should be 2x larger (150 → 300 DPI)
        assert upscaled.shape[0] == 200
        assert upscaled.shape[1] == 200

    def test_denoise(self):
        """Test denoising."""
        # Create noisy image
        img = np.random.randint(0, 255, (100, 100), dtype=np.uint8)

        denoised = self.preprocessor._denoise(img)

        # Denoised should have lower variance
        assert np.var(denoised) < np.var(img)

    def test_enhance_contrast(self):
        """Test contrast enhancement."""
        # Create low-contrast image
        img = np.full((100, 100), 128, dtype=np.uint8)
        img[25:75, 25:75] = 150

        enhanced = self.preprocessor._enhance_contrast(img)

        # Enhanced should have higher standard deviation
        assert np.std(enhanced) > np.std(img)


class TestDocumentAnalyzer:
    """Unit tests for document analyzer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = DocumentAnalyzer()

    def test_detect_skew(self):
        """Test skew detection."""
        # Create horizontal lines (0° skew)
        img = np.zeros((500, 500), dtype=np.uint8)
        for y in range(100, 400, 50):
            cv2.line(img, (50, y), (450, y), 255, 2)

        skew = self.analyzer._detect_skew(img)

        # Should detect ~0° skew
        assert abs(skew) < 2

    def test_measure_noise(self):
        """Test noise measurement."""
        # Clean image
        clean = np.zeros((100, 100), dtype=np.uint8)
        clean[25:75, 25:75] = 255

        # Noisy image
        noisy = clean + np.random.randint(-50, 50, (100, 100), dtype=np.int16)
        noisy = np.clip(noisy, 0, 255).astype(np.uint8)

        clean_noise = self.analyzer._measure_noise(clean)
        noisy_noise = self.analyzer._measure_noise(noisy)

        # Noisy image should have higher noise level
        assert noisy_noise > clean_noise

    def test_measure_contrast(self):
        """Test contrast measurement."""
        # High contrast
        high_contrast = np.zeros((100, 100), dtype=np.uint8)
        high_contrast[50:, :] = 255

        # Low contrast
        low_contrast = np.full((100, 100), 128, dtype=np.uint8)
        low_contrast[50:, :] = 140

        high_score = self.analyzer._measure_contrast(high_contrast)
        low_score = self.analyzer._measure_contrast(low_contrast)

        assert high_score > low_score
```

**Run unit tests:**

```bash
cd backend
pytest tests/test_ocr_preprocessor.py -v
```

Expected output:
```
test_ocr_preprocessor.py::TestOCRPreprocessor::test_deskew PASSED
test_ocr_preprocessor.py::TestOCRPreprocessor::test_upscale PASSED
test_ocr_preprocessor.py::TestOCRPreprocessor::test_denoise PASSED
test_ocr_preprocessor.py::TestOCRPreprocessor::test_enhance_contrast PASSED
test_ocr_preprocessor.py::TestDocumentAnalyzer::test_detect_skew PASSED
test_ocr_preprocessor.py::TestDocumentAnalyzer::test_measure_noise PASSED
test_ocr_preprocessor.py::TestDocumentAnalyzer::test_measure_contrast PASSED

============ 7 passed in 2.34s ============
```

### Integration Tests

Run full integration test with real documents:

```bash
pytest tests/test_ocr_integration.py -v
```

---

## Integration Verification

**Checklist:**

- [ ] OCRPreprocessor class created and working
- [ ] DocumentAnalyzer class created and working
- [ ] OCRService updated to use preprocessing
- [ ] Unit tests passing (7/7)
- [ ] Integration tests passing
- [ ] Benchmark showing 92%+ accuracy on clean docs
- [ ] Benchmark showing 88%+ accuracy on scanned docs
- [ ] Processing time < 5s per page
- [ ] No breaking changes to existing API
- [ ] All existing tests still passing

**Verification Commands:**

```bash
# Run all OCR-related tests
pytest tests/test_ocr*.py -v

# Run benchmark
python backend/scripts/benchmark_ocr.py

# Check no regression on existing tests
pytest backend/tests/ -v

# Test API endpoint still works
curl -X POST http://localhost:8000/api/upload \
  -F "file=@test_document.pdf" \
  -F "organization_id=1"
```

---

## Success Criteria

**Before marking this guide as complete, verify ALL of the following:**

✅ **Accuracy Targets Met:**
- [ ] Clean printed documents: ≥92% accuracy
- [ ] Scanned documents: ≥88% accuracy
- [ ] Overall accuracy improvement: ≥7% over baseline

✅ **Performance Targets Met:**
- [ ] Processing time: <5 seconds per page
- [ ] Memory usage: <500MB per document
- [ ] No crashes or errors in benchmark suite

✅ **Code Quality:**
- [ ] All unit tests passing (7/7 minimum)
- [ ] All integration tests passing
- [ ] Code properly documented with docstrings
- [ ] Type hints added to all functions
- [ ] Logging statements added for debugging

✅ **No Regressions:**
- [ ] Existing OCR functionality still works
- [ ] API endpoints unchanged
- [ ] All existing tests still passing
- [ ] No new dependencies break deployment

✅ **Documentation:**
- [ ] Code comments added for complex logic
- [ ] Benchmark results saved and reviewed
- [ ] Implementation tracker updated
- [ ] Any issues/blockers documented

---

## Troubleshooting

### Issue: Tesseract not found

**Error:** `TesseractNotFoundError`

**Solution:**
```bash
# Windows
choco install tesseract

# Mac
brew install tesseract

# Linux
sudo apt-get install tesseract-ocr

# Verify installation
tesseract --version
```

### Issue: OpenCV import error

**Error:** `ImportError: libGL.so.1: cannot open shared object file`

**Solution (Linux):**
```bash
sudo apt-get install libgl1-mesa-glx
```

### Issue: Low accuracy despite preprocessing

**Possible causes:**
1. Ground truth not accurate
2. Test documents too challenging
3. Preprocessing too aggressive

**Debug steps:**
```python
# Enable debug image saving
preprocessor.save_debug_image(preprocessed_img, "debug_output.png")

# Check preprocessing results visually
# Compare original vs preprocessed images
```

### Issue: Slow processing times

**Possible causes:**
1. Image resolution too high
2. Preprocessing too complex
3. Insufficient hardware

**Optimize:**
```python
# Reduce preprocessing steps for high-quality docs
if analysis['quality_score'] > 0.9:
    # Skip preprocessing
    pass
```

---

## Next Steps

**After completing OCR optimization:**

1. **Update Implementation Tracker** (`00_IMPLEMENTATION_TRACKER.md`):
   - Mark 01_OCR_OPTIMIZATION as ✅ Completed
   - Update metrics (accuracy achieved, time spent)
   - Document lessons learned

2. **Prepare for Next Phase:**
   - Review `02_DOCKER_SETUP.md` (if created)
   - Plan Docker development environment setup
   - Ensure OCR changes are committed to git

3. **Optional Enhancements** (if time permits):
   - Add support for multiple languages
   - Integrate Google Vision API for fallback
   - Implement caching for repeated documents

**Git Commit:**

```bash
git add backend/services/ocr/
git add backend/tests/test_ocr*.py
git add backend/scripts/benchmark_ocr.py
git commit -m "feat: Implement OCR optimization with 92%+ accuracy

- Add OCRPreprocessor with intelligent image preprocessing
- Add DocumentAnalyzer for quality detection
- Integrate preprocessing into OCRService
- Add comprehensive unit tests (7 tests)
- Add benchmark suite for accuracy measurement
- Achieve 92%+ accuracy on clean documents
- Achieve 88%+ accuracy on scanned documents

Closes #[issue-number]"

git push origin refactor/v2-architecture
```

---

**🎯 Goal:** By the end of this guide, you'll have a production-grade OCR system with **92%+ accuracy** on printed documents!

**⏱️ Time Investment:** 1-2 weeks (10-20 hours)

**💡 Remember:** Test frequently, commit often, and celebrate small wins!
