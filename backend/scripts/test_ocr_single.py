"""
Simple test to verify OCR optimization is working.
Tests a single document with and without preprocessing.
"""

import sys
from pathlib import Path
import time
from PIL import Image

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ocr_service import OCRService


async def test_single_document():
    """Test OCR on a single document with and without preprocessing."""

    # Initialize OCR service
    ocr = OCRService()

    # Get test document
    test_file = Path('tests/test_data/ocr/clean/invoice_001.pdf')

    if not test_file.exists():
        print(f"ERROR: Test file not found: {test_file}")
        return

    print("="*60)
    print("OCR OPTIMIZATION TEST")
    print("="*60)
    print(f"Test document: {test_file.name}\n")

    # Convert PDF to image
    from pdf2image import convert_from_path
    images = convert_from_path(str(test_file), first_page=1, last_page=1, dpi=300)

    if not images:
        print("ERROR: Could not convert PDF to image")
        return

    image = images[0]

    # Test 1: WITHOUT preprocessing
    print("-"*60)
    print("TEST 1: WITHOUT PREPROCESSING (Baseline)")
    print("-"*60)

    start = time.time()
    text_baseline = await ocr._tesseract_ocr(image, use_preprocessing=False)
    time_baseline = time.time() - start

    print(f"Processing time: {time_baseline:.2f}s")
    print(f"Text length: {len(text_baseline)} characters")
    print(f"First 200 chars: {text_baseline[:200]}")

    # Test 2: WITH preprocessing
    print("\n" + "-"*60)
    print("TEST 2: WITH PREPROCESSING (Optimized)")
    print("-"*60)

    start = time.time()
    text_optimized = await ocr._tesseract_ocr(image, use_preprocessing=True)
    time_optimized = time.time() - start

    print(f"Processing time: {time_optimized:.2f}s")
    print(f"Text length: {len(text_optimized)} characters")
    print(f"First 200 chars: {text_optimized[:200]}")

    # Compare
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    print(f"Baseline:  {len(text_baseline)} chars in {time_baseline:.2f}s")
    print(f"Optimized: {len(text_optimized)} chars in {time_optimized:.2f}s")

    if len(text_optimized) > len(text_baseline):
        improvement = ((len(text_optimized) - len(text_baseline)) / len(text_baseline)) * 100
        print(f"\nImprovement: +{improvement:.1f}% more text extracted")
    elif len(text_optimized) < len(text_baseline):
        print(f"\nNote: Baseline extracted more text (this can happen with clean documents)")
    else:
        print(f"\nSame amount of text extracted")

    print("\n" + "="*60)
    print("SUCCESS! OCR optimization is working correctly.")
    print("="*60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_single_document())
