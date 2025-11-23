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
import asyncio
from PIL import Image

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

    async def run_benchmark(self, use_preprocessing: bool = True) -> Dict:
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
        clean_results = await self._test_directory(
            self.test_data_dir / "clean",
            "Clean Printed Documents",
            use_preprocessing
        )

        # Test scanned documents
        scanned_results = await self._test_directory(
            self.test_data_dir / "scanned",
            "Scanned Documents",
            use_preprocessing
        )

        # Calculate overall results
        all_results = clean_results + scanned_results

        if not all_results:
            print("\n⚠️  No test documents found!")
            print("Please add documents to:")
            print(f"  - {self.test_data_dir / 'clean'}")
            print(f"  - {self.test_data_dir / 'scanned'}")
            print("And create ground truth files in:")
            print(f"  - {self.test_data_dir / 'ground_truth'}")
            return {
                'timestamp': datetime.now().isoformat(),
                'preprocessing_enabled': use_preprocessing,
                'total_documents': 0,
                'overall_accuracy': 0,
                'overall_confidence': 0,
                'avg_processing_time': 0,
                'clean_docs': {'count': 0, 'accuracy': 0, 'confidence': 0},
                'scanned_docs': {'count': 0, 'accuracy': 0, 'confidence': 0},
                'results': []
            }

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
                'accuracy': np.mean([r['accuracy'] for r in clean_results]) if clean_results else 0,
                'confidence': np.mean([r['confidence'] for r in clean_results]) if clean_results else 0
            },
            'scanned_docs': {
                'count': len(scanned_results),
                'accuracy': np.mean([r['accuracy'] for r in scanned_results]) if scanned_results else 0,
                'confidence': np.mean([r['confidence'] for r in scanned_results]) if scanned_results else 0
            },
            'results': all_results
        }

        self._print_summary(summary)
        self._save_results(summary)

        return summary

    async def _test_directory(self, dir_path: Path, label: str, use_preprocessing: bool) -> List[Dict]:
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

        if not dir_path.exists():
            print(f"⚠️  Directory not found: {dir_path}")
            return results

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
                import time
                start_time = time.time()

                # Load image
                image = Image.open(image_path)

                # Run OCR with preprocessing option
                extracted_text = await self.ocr_service._tesseract_ocr(
                    image,
                    use_preprocessing=use_preprocessing
                )

                processing_time = time.time() - start_time

                # Calculate accuracy
                accuracy = self._calculate_accuracy(ground_truth, extracted_text)

                # Estimate confidence (simplified - in real implementation, get from OCR)
                confidence = accuracy * 0.9  # Rough estimate

                result = {
                    'filename': image_path.name,
                    'accuracy': accuracy,
                    'confidence': confidence,
                    'processing_time': processing_time,
                    'preprocessing_applied': use_preprocessing
                }

                results.append(result)

                # Print result
                status = "✓" if accuracy >= 0.92 else "✗"
                print(f"{status} {image_path.name:30s} "
                      f"Accuracy: {accuracy*100:5.1f}%  "
                      f"Confidence: {confidence*100:5.1f}%  "
                      f"Time: {processing_time:.2f}s")

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
        output_dir.mkdir(exist_ok=True, parents=True)

        filename = f"ocr_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path = output_dir / filename

        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"✓ Results saved to: {output_path}")


async def main():
    """Run benchmark with and without preprocessing for comparison."""
    benchmark = OCRBenchmark()

    # Test WITHOUT preprocessing (baseline)
    print("\n" + "="*60)
    print("BASELINE TEST (No Preprocessing)")
    print("="*60)
    baseline_results = await benchmark.run_benchmark(use_preprocessing=False)

    # Test WITH preprocessing
    print("\n" + "="*60)
    print("OPTIMIZED TEST (With Preprocessing)")
    print("="*60)
    optimized_results = await benchmark.run_benchmark(use_preprocessing=True)

    # Compare results
    if baseline_results['total_documents'] > 0:
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
    asyncio.run(main())
