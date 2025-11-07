"""
API routes for document upload and processing.
Handles file uploads, background processing, status checking, and downloads.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List
import os
import uuid
from datetime import datetime
import asyncio
import time
from pathlib import Path

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import (
    BatchUploadResponse,
    BatchResultResponse,
    DocumentResult,
    ProcessingStatus,
    DocumentCategory
)
from services.ocr_service import OCRService
from services.ai_service import AIService
from services.file_service import FileService
from config import settings

# Create API router
router = APIRouter()

# In-memory storage for batch results (use Redis/DB in production)
# Format: {batch_id: {status, total_files, results, ...}}
batch_results = {}

# Initialize services (singleton pattern - create once, use throughout)
ocr_service = OCRService()
ai_service = AIService()
file_service = FileService()


@router.post("/upload", response_model=BatchUploadResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """
    Upload multiple PDF documents for processing.
    Processing happens in background, returns batch_id for status checking.

    Args:
        background_tasks: FastAPI background tasks handler
        files: List of uploaded PDF files

    Returns:
        BatchUploadResponse with batch_id and initial status

    Raises:
        HTTPException: If validation fails or file errors occur
    """
    # Validate files
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 files per batch")

    # Create unique batch ID
    batch_id = str(uuid.uuid4())
    upload_folder = os.path.join(settings.upload_dir, batch_id)
    os.makedirs(upload_folder, exist_ok=True)

    # Save uploaded files
    file_paths = []
    for file in files:
        # Validate file extension
        if not file.filename.endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file.filename}. Only PDF files allowed."
            )

        file_path = os.path.join(upload_folder, file.filename)

        # Save file and check size
        with open(file_path, 'wb') as f:
            content = await file.read()
            if len(content) > settings.max_file_size * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} exceeds maximum size of {settings.max_file_size}MB"
                )
            f.write(content)

        file_paths.append(file_path)

    # Initialize batch result tracking
    batch_results[batch_id] = {
        "status": ProcessingStatus.PENDING,
        "total_files": len(file_paths),
        "processed_files": 0,
        "results": [],
        "started_at": datetime.now(),
        "zip_path": None
    }

    # Start background processing
    background_tasks.add_task(process_batch, batch_id, file_paths)

    return BatchUploadResponse(
        batch_id=batch_id,
        total_files=len(file_paths),
        status=ProcessingStatus.PENDING,
        started_at=datetime.now()
    )


async def process_batch(batch_id: str, file_paths: List[str]):
    """
    Process all documents in the batch (runs in background).
    Orchestrates OCR, AI categorization, and file organization.

    Args:
        batch_id: Unique identifier for this batch
        file_paths: List of paths to uploaded PDF files
    """
    print(f"Starting batch processing: {batch_id} ({len(file_paths)} files)")
    batch_results[batch_id]["status"] = ProcessingStatus.PROCESSING

    # Process files with concurrency limit (avoid overwhelming system)
    semaphore = asyncio.Semaphore(settings.max_concurrent_processing)
    processed_results = []

    async def process_with_semaphore(file_path):
        """Wrapper to limit concurrent processing and update results incrementally"""
        async with semaphore:
            try:
                result = await process_single_document(file_path)
            except Exception as e:
                # Create error result for failed document
                result = DocumentResult(
                    filename=os.path.basename(file_path),
                    original_path=file_path,
                    category=DocumentCategory.OTHER,
                    confidence=0.0,
                    extracted_text_preview="",
                    extracted_data=None,
                    error=str(e),
                    processing_time=0.0
                )

            # Update results incrementally so frontend can show progress
            processed_results.append(result)
            batch_results[batch_id]["results"] = processed_results.copy()
            batch_results[batch_id]["processed_files"] = len(processed_results)

            return result

    # Process all files concurrently (up to semaphore limit)
    tasks = [process_with_semaphore(fp) for fp in file_paths]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Organize files and create ZIP
    try:
        zip_path = await file_service.organize_documents(processed_results)
        download_url = f"/download/{batch_id}"
        batch_results[batch_id]["zip_path"] = zip_path
    except Exception as e:
        print(f"Failed to organize documents: {e}")
        download_url = None

    # Calculate statistics
    successful = sum(1 for r in processed_results if r.error is None)
    failed = len(processed_results) - successful

    # Calculate summary by category
    category_summary = {}
    for result in processed_results:
        if result.error is None:
            cat_name = result.category
            category_summary[cat_name] = category_summary.get(cat_name, 0) + 1

    # Update batch results with final data
    batch_results[batch_id].update({
        "status": ProcessingStatus.COMPLETED,
        "processed_files": len(processed_results),
        "results": processed_results,
        "successful": successful,
        "failed": failed,
        "processing_summary": category_summary,
        "download_url": download_url
    })

    print(f"Batch processing completed: {batch_id} ({successful} successful, {failed} failed)")


async def process_single_document(file_path: str) -> DocumentResult:
    """
    Process a single document through the full pipeline:
    1. OCR text extraction
    2. Quality validation
    3. AI categorization

    Args:
        file_path: Path to the PDF file

    Returns:
        DocumentResult with categorization and metadata
    """
    start_time = time.time()
    filename = os.path.basename(file_path)

    try:
        print(f"Processing: {filename}")

        # Step 1: OCR - Extract text from PDF
        extracted_text = await ocr_service.extract_text_from_pdf(file_path)

        # Validate OCR quality
        if not ocr_service.validate_ocr_quality(extracted_text):
            raise Exception("OCR quality check failed - insufficient text extracted")

        # Step 2: AI Categorization and Data Extraction
        category, confidence, extracted_data = await ai_service.categorize_document(extracted_text, filename)

        # Create preview (first 500 chars)
        text_preview = extracted_text[:500] if extracted_text else ""

        processing_time = time.time() - start_time

        print(f"✓ {filename} -> {category.value} (confidence: {confidence:.2f}, time: {processing_time:.2f}s)")

        return DocumentResult(
            filename=filename,
            original_path=file_path,
            category=category,
            confidence=confidence,
            extracted_text_preview=text_preview,
            extracted_data=extracted_data,
            error=None,
            processing_time=processing_time
        )

    except Exception as e:
        processing_time = time.time() - start_time
        print(f"✗ {filename} failed: {str(e)}")

        return DocumentResult(
            filename=filename,
            original_path=file_path,
            category=DocumentCategory.OTHER,
            confidence=0.0,
            extracted_text_preview="",
            extracted_data=None,
            error=str(e),
            processing_time=processing_time
        )


@router.get("/status/{batch_id}", response_model=BatchResultResponse)
async def get_batch_status(batch_id: str):
    """
    Get the processing status of a batch.
    Frontend polls this endpoint to show progress.

    Args:
        batch_id: Unique batch identifier

    Returns:
        BatchResultResponse with current status and results

    Raises:
        HTTPException: If batch_id not found
    """
    if batch_id not in batch_results:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = batch_results[batch_id]

    return BatchResultResponse(
        batch_id=batch_id,
        status=batch["status"],
        total_files=batch["total_files"],
        processed_files=batch["processed_files"],
        successful=batch.get("successful", 0),
        failed=batch.get("failed", 0),
        results=batch.get("results", []),
        processing_summary=batch.get("processing_summary", {}),
        download_url=batch.get("download_url")
    )


@router.get("/download/{batch_id}")
async def download_results(batch_id: str):
    """
    Download the organized documents as a ZIP file.

    Args:
        batch_id: Unique batch identifier

    Returns:
        FileResponse with ZIP file

    Raises:
        HTTPException: If batch not found or not ready
    """
    if batch_id not in batch_results:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = batch_results[batch_id]

    if batch["status"] != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Batch processing not complete")

    zip_path = batch.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Results file not found")

    return FileResponse(
        path=zip_path,
        filename=f"processed_documents_{batch_id}.zip",
        media_type="application/zip"
    )
