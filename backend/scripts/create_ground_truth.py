"""
Helper script to create ground truth text files for OCR testing.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ocr_service import get_ocr_service


def extract_ground_truth():
    """Extract text from test documents to create ground truth files."""
    ocr = get_ocr_service()
    test_files = Path('tests/test_data/ocr/clean').glob('*.pdf')

    count = 0
    for pdf_file in test_files:
        print(f'Extracting text from {pdf_file.name}...')
        result = ocr.extract_text_from_file(str(pdf_file))
        text = result['text']

        # Save as ground truth
        gt_file = Path('tests/test_data/ocr/ground_truth') / f'{pdf_file.stem}.txt'
        with open(gt_file, 'w', encoding='utf-8') as f:
            f.write(text)

        print(f'✓ Created ground truth: {gt_file.name} ({len(text)} chars)')
        count += 1

    print(f'\n✓ Created {count} ground truth files')


if __name__ == "__main__":
    extract_ground_truth()
