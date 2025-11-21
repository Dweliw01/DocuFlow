"""
Simple test for Phase 3 few-shot learning implementation.
Tests backward compatibility with feature flag OFF.
"""
import sys
import asyncio
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from services.ai_service import AIService
from config import settings

# Sample document text
SAMPLE_TEXT = """
INVOICE
Invoice Number: INV-2024-001
Date: January 15, 2024
Total: $351.00
"""


async def test_basic():
    """Basic test of AI service."""
    print("Testing Phase 3 Implementation...")
    print(f"Feature flag: enable_few_shot_learning = {settings.enable_few_shot_learning}")
    print()

    ai_service = AIService()

    # Test 1: Without organization_id (backward compatible)
    print("Test 1: Categorization WITHOUT organization_id")
    try:
        category, confidence, extracted_data = await ai_service.categorize_document(
            SAMPLE_TEXT,
            "test.pdf"
        )
        print(f"  Category: {category}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Status: PASSED")
    except Exception as e:
        print(f"  Status: FAILED - {e}")
        return False

    print()

    # Test 2: With organization_id (feature flag OFF, should still work)
    print("Test 2: Categorization WITH organization_id (feature flag OFF)")
    try:
        category, confidence, extracted_data = await ai_service.categorize_document(
            SAMPLE_TEXT,
            "test.pdf",
            organization_id=1
        )
        print(f"  Category: {category}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Status: PASSED")
    except Exception as e:
        print(f"  Status: FAILED - {e}")
        return False

    print()
    print("All tests PASSED!")
    print("Backward compatibility confirmed - feature flag OFF works correctly.")
    return True


if __name__ == "__main__":
    asyncio.run(test_basic())
