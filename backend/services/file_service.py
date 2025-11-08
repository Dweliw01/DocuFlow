"""
File Service for organizing processed documents.
Creates category folders, generates processing logs, and creates ZIP files.
"""
import os
import shutil
import zipfile
from pathlib import Path
from typing import List
import aiofiles
from datetime import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import DocumentResult, DocumentCategory
from config import settings


class FileService:
    """
    Service for organizing and packaging processed documents.
    Creates organized folder structure and ZIP files for download.
    """

    def __init__(self):
        """Initialize file service with processed directory from settings."""
        self.processed_dir = settings.processed_dir
        print("[OK] File Service initialized")

    async def organize_documents(self, results: List[DocumentResult]) -> str:
        """
        Organize processed documents into category folders and create a ZIP file.

        Creates structure like:
        batch_20240115_143022/
        ├── Invoice/
        │   ├── [Invoice] document1.pdf
        │   └── [Invoice] document2.pdf
        ├── Contract/
        │   └── [Contract] agreement.pdf
        └── PROCESSING_LOG.txt

        Args:
            results: List of DocumentResult objects

        Returns:
            Path to the created ZIP file
        """
        # Create timestamp for this batch
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_folder = os.path.join(self.processed_dir, f"batch_{timestamp}")

        # Create category folders for all possible categories
        for category in DocumentCategory:
            category_path = os.path.join(batch_folder, category.value)
            os.makedirs(category_path, exist_ok=True)

        # Move files to appropriate categories
        for result in results:
            if result.processed_path is None and result.error is None:
                # Get category value (handle both enum and string)
                category_name = result.category.value if hasattr(result.category, 'value') else str(result.category)

                # Copy file to category folder
                dest_folder = os.path.join(batch_folder, category_name)

                # Add category prefix to filename for easy identification
                name, ext = os.path.splitext(result.filename)
                new_filename = f"[{category_name}] {name}{ext}"
                dest_path = os.path.join(dest_folder, new_filename)

                # Copy the file
                shutil.copy2(result.original_path, dest_path)
                result.processed_path = dest_path

        # Create processing log
        await self._create_processing_log(batch_folder, results)

        # Create ZIP file
        zip_path = f"{batch_folder}.zip"
        await self._create_zip(batch_folder, zip_path)

        return zip_path

    async def _create_processing_log(self, batch_folder: str, results: List[DocumentResult]):
        """
        Create a detailed processing log file.
        Includes summary statistics and detailed results for each document.

        Args:
            batch_folder: Path to the batch folder
            results: List of DocumentResult objects
        """
        log_path = os.path.join(batch_folder, "PROCESSING_LOG.txt")

        async with aiofiles.open(log_path, 'w', encoding='utf-8') as f:
            # Header
            await f.write("=" * 80 + "\n")
            await f.write("DOCUMENT PROCESSING LOG\n")
            await f.write("=" * 80 + "\n\n")
            await f.write(f"Processing Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            await f.write(f"Total Documents: {len(results)}\n")

            # Summary by category
            await f.write("\n" + "-" * 80 + "\n")
            await f.write("SUMMARY BY CATEGORY\n")
            await f.write("-" * 80 + "\n")

            # Count documents per category
            category_counts = {}
            for result in results:
                if result.error is None:  # Only count successful ones
                    category_counts[result.category] = category_counts.get(result.category, 0) + 1

            # Sort by category name and write
            for category in sorted(category_counts.keys(), key=lambda x: x.value if hasattr(x, 'value') else str(x)):
                category_name = category.value if hasattr(category, 'value') else str(category)
                await f.write(f"{category_name}: {category_counts[category]} documents\n")

            # Error summary
            error_count = sum(1 for r in results if r.error is not None)
            if error_count > 0:
                await f.write(f"\nErrors: {error_count} documents failed to process\n")

            # Detailed results
            await f.write("\n" + "-" * 80 + "\n")
            await f.write("DETAILED RESULTS\n")
            await f.write("-" * 80 + "\n\n")

            for i, result in enumerate(results, 1):
                category_name = result.category.value if hasattr(result.category, 'value') else str(result.category)
                await f.write(f"{i}. {result.filename}\n")
                await f.write(f"   Category: {category_name}\n")
                await f.write(f"   Confidence: {result.confidence:.2%}\n")
                await f.write(f"   Processing Time: {result.processing_time:.2f}s\n")

                if result.error:
                    await f.write(f"   ERROR: {result.error}\n")
                else:
                    # Show extracted data if available
                    if result.extracted_data:
                        await f.write(f"   \n   EXTRACTED DATA:\n")
                        data = result.extracted_data

                        if data.document_type:
                            await f.write(f"   - Document Type: {data.document_type}\n")
                        if data.person_name:
                            await f.write(f"   - Person Name: {data.person_name}\n")
                        if data.company:
                            await f.write(f"   - Company: {data.company}\n")
                        if data.vendor:
                            await f.write(f"   - Vendor: {data.vendor}\n")
                        if data.client:
                            await f.write(f"   - Client: {data.client}\n")
                        if data.date:
                            await f.write(f"   - Date: {data.date}\n")
                        if data.due_date:
                            await f.write(f"   - Due Date: {data.due_date}\n")
                        if data.amount:
                            await f.write(f"   - Amount: {data.amount}\n")
                        if data.currency:
                            await f.write(f"   - Currency: {data.currency}\n")
                        if data.document_number:
                            await f.write(f"   - Document Number: {data.document_number}\n")
                        if data.reference_number:
                            await f.write(f"   - Reference Number: {data.reference_number}\n")
                        if data.address:
                            await f.write(f"   - Address: {data.address}\n")
                        if data.email:
                            await f.write(f"   - Email: {data.email}\n")
                        if data.phone:
                            await f.write(f"   - Phone: {data.phone}\n")
                        if data.line_items:
                            await f.write(f"   - Line Items ({len(data.line_items)} items):\n")
                            for idx, item in enumerate(data.line_items[:10], 1):  # Limit to first 10 items in log
                                await f.write(f"     {idx}. {item.description or 'N/A'}")
                                if item.quantity:
                                    await f.write(f" | Qty: {item.quantity}")
                                if item.unit_price:
                                    await f.write(f" | Price: {item.unit_price}")
                                if item.amount:
                                    await f.write(f" | Total: {item.amount}")
                                await f.write("\n")
                            if len(data.line_items) > 10:
                                await f.write(f"     ... and {len(data.line_items) - 10} more items\n")
                        if data.other_data:
                            await f.write(f"   - Other Data:\n")
                            for key, value in data.other_data.items():
                                await f.write(f"     * {key}: {value}\n")

                    # Show first 150 chars of extracted text as preview
                    preview = result.extracted_text_preview[:150].replace('\n', ' ')
                    await f.write(f"   \n   Text Preview: {preview}...\n")
                await f.write("\n")

    async def _create_zip(self, source_folder: str, zip_path: str):
        """
        Create ZIP file of the processed documents.
        Includes all category folders and the processing log.

        Args:
            source_folder: Path to folder to zip
            zip_path: Path where ZIP file should be created
        """
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Create relative path for inside the ZIP
                    arcname = os.path.relpath(file_path, source_folder)
                    zipf.write(file_path, arcname)

    async def cleanup_old_files(self, days: int = 7):
        """
        Clean up files older than specified days.
        Helps prevent disk space issues in production.

        Args:
            days: Number of days after which files should be deleted
        """
        cutoff_time = datetime.now().timestamp() - (days * 86400)

        for folder in [settings.upload_dir, settings.processed_dir]:
            if not os.path.exists(folder):
                continue

            for item in os.listdir(folder):
                item_path = os.path.join(folder, item)

                try:
                    if os.path.getmtime(item_path) < cutoff_time:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        print(f"Cleaned up old file: {item}")
                except Exception as e:
                    print(f"Failed to clean up {item}: {e}")
