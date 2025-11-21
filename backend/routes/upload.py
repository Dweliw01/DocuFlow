"""
API routes for document upload and processing.
Handles file uploads, background processing, status checking, and downloads.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from typing import List
import os
import uuid
from datetime import datetime
import asyncio
import time
import logging
import json
from pathlib import Path

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import (
    BatchUploadResponse,
    BatchResultResponse,
    DocumentResult,
    ProcessingStatus,
    DocumentCategory,
    ConnectorType,
    UploadResult
)
from services.ocr_service import OCRService
from services.ai_service import AIService
from services.file_service import FileService
from services.encryption_service import get_encryption_service
from services.confidence_service import calculate_overall_confidence, add_confidence_to_extracted_data
from services.auto_upload_service import process_document_for_review
from services.ai_learning_service import get_ai_learning_service
from connectors.connector_manager import get_connector_manager
from routes.connector_routes import get_current_config_with_decrypted_password
from config import settings
from auth import get_current_user
from database import create_batch, update_batch, get_batch, get_subscription, get_usage_stats, log_usage, get_user_batches, get_db_connection, get_user_by_id

# Import plan configuration
sys.path.append(str(Path(__file__).parent.parent))
from plan_config import check_usage_limit, is_trial_expired

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter()


# ============================================================================
# Helper Functions for Google Drive Folder Structure
# ============================================================================

def get_google_drive_fields_from_folder_config(google_drive_config) -> List[str]:
    """
    Extract field names needed based on Google Drive folder structure configuration.
    Maps folder structure levels to field names that need to be extracted.

    Args:
        google_drive_config: GoogleDriveConfig object with folder structure settings

    Returns:
        List of field names to extract (e.g., ['vendor', 'date', 'category'])
    """
    from models import FolderStructureLevel

    fields_needed = []

    # Map folder structure levels to field names
    level_to_field_map = {
        FolderStructureLevel.CATEGORY: 'category',
        FolderStructureLevel.VENDOR: 'vendor',
        FolderStructureLevel.CLIENT: 'client',
        FolderStructureLevel.COMPANY: 'company',
        FolderStructureLevel.YEAR: 'date',  # Need date to extract year
        FolderStructureLevel.YEAR_MONTH: 'date',  # Need date to extract year-month
        FolderStructureLevel.MONTH: 'date',  # Need date to extract month
        FolderStructureLevel.QUARTER: 'date',  # Need date to extract quarter
        FolderStructureLevel.DOCUMENT_TYPE: 'document_type',
        FolderStructureLevel.DOCUMENT_NUMBER: 'document_number',
        FolderStructureLevel.PERSON_NAME: 'person_name',
        FolderStructureLevel.PROJECT: 'project',
        FolderStructureLevel.CUSTOM: None,  # Will use custom field name
        FolderStructureLevel.NONE: None  # Skip
    }

    # Check primary level
    primary_value = google_drive_config.primary_level.value if hasattr(google_drive_config.primary_level, 'value') else google_drive_config.primary_level
    if primary_value == 'custom':
        if google_drive_config.primary_custom_field:
            fields_needed.append(google_drive_config.primary_custom_field)
    elif google_drive_config.primary_level in level_to_field_map:
        field = level_to_field_map[google_drive_config.primary_level]
        if field and field not in fields_needed:
            fields_needed.append(field)

    # Check secondary level
    secondary_value = google_drive_config.secondary_level.value if hasattr(google_drive_config.secondary_level, 'value') else google_drive_config.secondary_level
    if secondary_value == 'custom':
        if google_drive_config.secondary_custom_field:
            fields_needed.append(google_drive_config.secondary_custom_field)
    elif google_drive_config.secondary_level in level_to_field_map:
        field = level_to_field_map[google_drive_config.secondary_level]
        if field and field not in fields_needed:
            fields_needed.append(field)

    # Check tertiary level
    tertiary_value = google_drive_config.tertiary_level.value if hasattr(google_drive_config.tertiary_level, 'value') else google_drive_config.tertiary_level
    if tertiary_value == 'custom':
        if google_drive_config.tertiary_custom_field:
            fields_needed.append(google_drive_config.tertiary_custom_field)
    elif google_drive_config.tertiary_level in level_to_field_map:
        field = level_to_field_map[google_drive_config.tertiary_level]
        if field and field not in fields_needed:
            fields_needed.append(field)

    return fields_needed

# Initialize services (singleton pattern - create once, use throughout)
ocr_service = OCRService()
ai_service = AIService()
file_service = FileService()
encryption_service = get_encryption_service()
connector_manager = get_connector_manager()
ai_learning_service = get_ai_learning_service()


@router.post("/upload", response_model=BatchUploadResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload multiple PDF documents for processing.
    Processing happens in background, returns batch_id for status checking.
    Requires authentication.

    Args:
        background_tasks: FastAPI background tasks handler
        files: List of uploaded PDF files
        current_user: Authenticated user from JWT token

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

    # Check organization and subscription limits
    org_id = current_user.get("organization_id")
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="User must belong to an organization to upload documents"
        )

    # Get subscription
    subscription = await get_subscription(org_id)
    if not subscription:
        raise HTTPException(
            status_code=403,
            detail="No active subscription found"
        )

    # Check if trial has expired
    trial_end_date = subscription.get("trial_end_date")
    if trial_end_date:
        try:
            if is_trial_expired(trial_end_date):
                raise HTTPException(
                    status_code=402,
                    detail="Your trial has expired. Please upgrade your plan to continue processing documents."
                )
        except Exception as e:
            logger.warning(f"Could not check trial expiration: {str(e)}")

    # Get current usage for billing period
    billing_period = datetime.now().strftime("%Y-%m")
    usage_stats = await get_usage_stats(org_id, billing_period)
    current_usage = usage_stats.get("total_documents_processed", 0)

    # Check usage limits
    plan_type = subscription.get("plan_type", "trial")
    limit_check = check_usage_limit(plan_type, current_usage, len(files))

    if not limit_check.get("allowed"):
        raise HTTPException(
            status_code=402,
            detail=limit_check.get("reason") +
                   f" (Current: {current_usage}, Trying to add: {len(files)}, Limit: {limit_check.get('limit')})"
        )

    # Create unique batch ID
    batch_id = str(uuid.uuid4())
    user_id = current_user["id"]

    # Create user-scoped upload folder
    upload_folder = os.path.join(settings.upload_dir, str(user_id), batch_id)
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

    # Create batch record in database
    await create_batch(batch_id, user_id, len(file_paths))

    # Start background processing
    background_tasks.add_task(process_batch, batch_id, user_id, file_paths)

    return BatchUploadResponse(
        batch_id=batch_id,
        total_files=len(file_paths),
        status=ProcessingStatus.PENDING,
        started_at=datetime.now()
    )


async def process_batch(batch_id: str, user_id: int, file_paths: List[str]):
    """
    Process all documents in the batch (runs in background).
    Orchestrates OCR, AI categorization, and file organization.

    Args:
        batch_id: Unique identifier for this batch
        user_id: User ID who owns this batch
        file_paths: List of paths to uploaded PDF files
    """
    print(f"\n{'='*60}")
    print(f"📦 Starting batch processing: {batch_id} (User: {user_id})")
    print(f"   Files to process: {len(file_paths)}")
    print(f"{'='*60}\n")
    logger.info(f"Starting batch processing: {batch_id} ({len(file_paths)} files) for user {user_id}")

    # Get user's organization for review workflow
    user = await get_user_by_id(user_id)
    organization_id = user.get("organization_id") if user else None

    # Process files with concurrency limit (avoid overwhelming system)
    semaphore = asyncio.Semaphore(settings.max_concurrent_processing)
    processed_results = []

    async def process_with_semaphore(file_path):
        """Wrapper to limit concurrent processing and update results incrementally"""
        async with semaphore:
            try:
                result = await process_single_document(file_path, user_id)
            except Exception as e:
                # Create error result for failed document
                result = DocumentResult(
                    filename=os.path.basename(file_path),
                    original_path=file_path,
                    category=DocumentCategory.OTHER,
                    confidence=0.0,
                    extracted_text_preview="",
                    extracted_data=None,
                    connector_type=None,  # Failed before connector determination
                    error=str(e),
                    processing_time=0.0
                )

            # Save to document_metadata and run review workflow
            if organization_id and result.error is None and result.extracted_data:
                try:
                    # Convert Pydantic model to dict for confidence service
                    extracted_data_dict = result.extracted_data.dict() if hasattr(result.extracted_data, 'dict') else result.extracted_data.model_dump()

                    # Calculate confidence score
                    confidence_score = calculate_overall_confidence(extracted_data_dict)

                    # Add confidence to extracted data fields
                    scored_data = add_confidence_to_extracted_data(extracted_data_dict)

                    # Save to document_metadata table
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    try:
                        cursor.execute('''
                            INSERT INTO document_metadata
                            (organization_id, batch_id, filename, file_path, category,
                             extracted_data, status, confidence_score, connector_type, connector_config_snapshot, processed_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            organization_id,
                            batch_id,
                            result.filename,
                            file_path,
                            result.category.value if hasattr(result.category, 'value') else str(result.category),
                            json.dumps(scored_data),  # Store as JSON string
                            'pending_review',  # Initial status
                            confidence_score,
                            result.connector_type,  # Store which connector this document was processed with
                            result.connector_config_snapshot,  # Store config snapshot for historical field display
                            datetime.utcnow()
                        ))
                        conn.commit()
                        doc_id = cursor.lastrowid

                        # Set document ID on result for frontend (enables Review button)
                        result.id = doc_id

                        # Run review workflow to determine if should auto-upload
                        review_result = await process_document_for_review(
                            doc_id,
                            organization_id,
                            confidence_score
                        )

                        logger.info(
                            f"Document {doc_id} ({result.filename}): "
                            f"{review_result['status']} (confidence: {confidence_score:.2f})"
                        )

                    finally:
                        conn.close()

                except Exception as e:
                    logger.error(f"Failed to save document metadata for {result.filename}: {e}")

            # Update results incrementally so frontend can show progress
            processed_results.append(result)

            # Update database with current progress
            await update_batch(
                batch_id=batch_id,
                status="processing",
                processed_files=len(processed_results),
                successful=0,
                failed=0,
                results=[r.dict() for r in processed_results]
            )

            return result

    # Process all files concurrently (up to semaphore limit)
    tasks = [process_with_semaphore(fp) for fp in file_paths]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Organize files and create ZIP
    try:
        zip_path = await file_service.organize_documents(processed_results)
        download_url = f"/api/download/{batch_id}"
    except Exception as e:
        logger.error(f"Failed to organize documents: {e}")
        download_url = None

    # NOTE: Connector upload is now handled by the review workflow
    # Documents go through review (or auto-upload based on confidence)
    # and are uploaded when approved via the document approval endpoint
    # await upload_to_connector(processed_results, user_id)

    # Calculate statistics
    successful = sum(1 for r in processed_results if r.error is None)
    failed = len(processed_results) - successful

    # Calculate summary by category
    category_summary = {}
    for result in processed_results:
        if result.error is None:
            cat_name = result.category
            category_summary[cat_name] = category_summary.get(cat_name, 0) + 1

    # Update database with final results
    await update_batch(
        batch_id=batch_id,
        status="completed",
        processed_files=len(processed_results),
        successful=successful,
        failed=failed,
        results=[r.dict() for r in processed_results],
        processing_summary=category_summary,
        download_url=download_url
    )

    # Log usage for successful documents (for billing)
    if successful > 0:
        try:
            # Get user's organization from database
            user = await get_user_by_id(user_id)
            if user and user.get("organization_id"):
                await log_usage(
                    org_id=user["organization_id"],
                    action_type="document_processed",
                    document_count=successful,
                    user_id=user_id,
                    metadata={
                        "batch_id": batch_id,
                        "total_files": len(processed_results),
                        "failed": failed,
                        "categories": category_summary
                    }
                )
                logger.info(f"Logged usage: {successful} documents for org {user['organization_id']}")
        except Exception as e:
            logger.error(f"Failed to log usage: {str(e)}")

    print(f"\n{'='*60}")
    print(f"✅ Batch processing completed: {batch_id}")
    print(f"   ✓ Successful: {successful}")
    print(f"   ✗ Failed: {failed}")
    print(f"{'='*60}\n")
    logger.info(f"Batch processing completed: {batch_id} ({successful} successful, {failed} failed)")


async def process_single_document(file_path: str, user_id: int) -> DocumentResult:
    """
    Process a single document through the full pipeline:
    1. OCR text extraction
    2. Quality validation
    3. AI categorization with dynamic field extraction

    Args:
        file_path: Path to the PDF file
        user_id: User ID for loading their connector configuration

    Returns:
        DocumentResult with categorization and metadata
    """
    start_time = time.time()
    filename = os.path.basename(file_path)

    try:
        print(f"⚙️  Processing: {filename}")
        logger.info(f"Processing: {filename}")

        # Step 1: Extract text from file (supports PDFs and images)
        extraction_result = ocr_service.extract_text_from_file(file_path)
        extracted_text = extraction_result.get('text', '')
        extraction_method = extraction_result.get('method', 'unknown')
        file_type = extraction_result.get('file_type', 'unknown')

        logger.info(f"Text extraction: method={extraction_method}, file_type={file_type}, chars={len(extracted_text)}")

        # Extract OCR coordinates for images and image-based PDFs
        ocr_coordinates_path = None
        if extraction_method in ['image_ocr', 'pdf_ocr']:
            try:
                logger.info(f"Extracting OCR coordinates for {filename}")
                ocr_data = ocr_service.extract_text_with_coordinates(file_path)

                # Save coordinates to JSON file
                if ocr_data and ocr_data.get('words'):
                    coords_filename = f"{os.path.splitext(filename)[0]}_ocr_coordinates.json"
                    coords_dir = os.path.dirname(file_path)
                    ocr_coordinates_path = os.path.join(coords_dir, coords_filename)

                    with open(ocr_coordinates_path, 'w', encoding='utf-8') as f:
                        json.dump(ocr_data, f, indent=2)

                    logger.info(f"Saved OCR coordinates: {len(ocr_data['words'])} words -> {coords_filename}")
            except Exception as e:
                logger.warning(f"Failed to extract OCR coordinates for {filename}: {e}")

        # Validate text quality
        if not ocr_service.validate_ocr_quality(extracted_text):
            raise Exception(f"Text quality check failed - insufficient text extracted (method: {extraction_method})")

        # Get user's organization_id for few-shot learning
        organization_id = None
        user = await get_user_by_id(user_id)
        if user and user.get('organization_id'):
            organization_id = user['organization_id']

        # Get selected fields from connector config (if configured)
        selected_fields = None
        selected_table_columns = None
        connector_type = None
        connector_config_json = None
        config_tuple = await get_current_config_with_decrypted_password(user_id)
        if config_tuple:
            connector_config, _ = config_tuple
            connector_type = connector_config.connector_type
            # Save connector config snapshot for historical field display
            connector_config_json = connector_config.model_dump_json() if hasattr(connector_config, 'model_dump_json') else connector_config.json()

            # DocuWare: Extract user-selected fields
            if connector_config.connector_type == "docuware" and connector_config.docuware:
                selected_fields = connector_config.docuware.selected_fields
                selected_table_columns = connector_config.docuware.selected_table_columns
                logger.info(f"[UPLOAD DEBUG] Loaded DocuWare config - {len(selected_fields)} fields, table_columns: {list(selected_table_columns.keys()) if selected_table_columns else 'None'}")

            # Google Drive: Extract fields based on folder structure configuration
            elif connector_config.connector_type == "google_drive" and connector_config.google_drive:
                selected_fields = get_google_drive_fields_from_folder_config(connector_config.google_drive)
                logger.info(f"[Google Drive] Extracting fields for folder structure: {selected_fields}")

        # Step 2: AI Categorization and Data Extraction (dynamic if fields selected, with few-shot learning)
        category, confidence, extracted_data = await ai_service.categorize_document(
            extracted_text,
            filename,
            selected_fields=selected_fields,
            selected_table_columns=selected_table_columns,
            organization_id=organization_id  # Phase 3: Few-shot learning
        )

        # Step 3: AI Learning - Apply learned suggestions and adjust confidence
        try:
            if organization_id:
                # Convert ExtractedData model to dict for AI learning
                extracted_data_dict = extracted_data.model_dump() if hasattr(extracted_data, 'model_dump') else (
                    extracted_data.dict() if hasattr(extracted_data, 'dict') else extracted_data
                )

                # Apply learned suggestions based on correction history
                enhanced_data, applied_suggestions = ai_learning_service.apply_learned_suggestions(
                    extracted_data_dict,
                    organization_id,
                    category=category.value if category else None
                )

                if applied_suggestions:
                    logger.info(f"[AI LEARNING] Applied {len(applied_suggestions)} learned suggestions: {', '.join(applied_suggestions)}")
                    extracted_data_dict = enhanced_data

                # Adjust confidence scores based on error-prone fields
                extracted_data_dict = ai_learning_service.adjust_confidence_with_learning(
                    extracted_data_dict,
                    organization_id,
                    category=category.value if category else None
                )

                # Convert the enhanced dict back to ExtractedData model
                from services.connector_service import _build_extracted_data
                extracted_data = _build_extracted_data(extracted_data_dict)

        except Exception as e:
            logger.warning(f"[AI LEARNING] Error applying learning: {e}")
            # Continue processing even if learning fails

        # Create preview (first 500 chars)
        text_preview = extracted_text[:500] if extracted_text else ""

        processing_time = time.time() - start_time

        print(f"   ✅ {filename} -> {category.value} (confidence: {confidence:.2f}, time: {processing_time:.2f}s)")
        logger.info(f"✓ {filename} -> {category.value} (confidence: {confidence:.2f}, time: {processing_time:.2f}s)")

        return DocumentResult(
            filename=filename,
            original_path=file_path,
            category=category,
            confidence=confidence,
            extracted_text_preview=text_preview,
            extracted_data=extracted_data,
            connector_type=connector_type,
            connector_config_snapshot=connector_config_json,
            error=None,
            processing_time=processing_time
        )

    except Exception as e:
        processing_time = time.time() - start_time
        print(f"   ❌ {filename} failed: {str(e)}")
        logger.error(f"✗ {filename} failed: {str(e)}")

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


async def upload_to_connector(results: List[DocumentResult], user_id: int):
    """
    Upload processed documents to configured connector.
    Only uploads successfully processed documents with extracted data.

    Args:
        results: List of DocumentResult objects to upload
        user_id: User ID for loading their connector configuration
    """
    # Get current connector configuration for this user
    config_tuple = await get_current_config_with_decrypted_password(user_id)

    if not config_tuple:
        # No connector configured for this user
        logger.info(f"No connector configured for user {user_id} - skipping uploads")
        return

    config, decrypted_password = config_tuple

    if config.connector_type == ConnectorType.NONE:
        # Connector explicitly set to None
        return

    print(f"\n{'='*60}")
    print(f"📤 Uploading documents to {config.connector_type}")
    print(f"{'='*60}\n")
    logger.info(f"Uploading documents to {config.connector_type}...")

    # Upload each successfully processed document
    upload_count = 0
    for result in results:
        # Skip failed documents or documents without processed path
        if result.error is not None or result.processed_path is None:
            continue

        # Skip documents without extracted data
        if result.extracted_data is None:
            print(f"   ⏭️  Skipping {result.filename} - no extracted data")
            logger.debug(f"Skipping {result.filename} - no extracted data")
            continue

        try:
            # Upload to connector
            upload_result = await connector_manager.upload_document(
                file_path=result.processed_path,
                extracted_data=result.extracted_data,
                config=config,
                decrypted_password=decrypted_password,
                category=result.category  # Pass the AI-detected category for folder organization
            )

            # Store upload result
            result.upload_result = upload_result

            if upload_result.success:
                upload_count += 1
                print(f"   ✅ Uploaded: {result.filename}")
                logger.info(f"✓ Uploaded {result.filename} to {config.connector_type}")
            else:
                print(f"   ❌ Upload failed: {result.filename} - {upload_result.error}")
                logger.warning(f"✗ Failed to upload {result.filename}: {upload_result.error}")

        except Exception as e:
            print(f"   ❌ Upload error: {result.filename} - {str(e)}")
            logger.error(f"✗ Upload error for {result.filename}: {str(e)}")
            result.upload_result = UploadResult(
                success=False,
                message="Upload error",
                error=str(e)
            )

    print(f"\n{'='*60}")
    print(f"📊 Upload Summary")
    print(f"   Uploaded: {upload_count}/{len(results)} documents")
    print(f"{'='*60}\n")
    logger.info(f"Connector upload completed: {upload_count}/{len(results)} documents uploaded")


@router.get("/status/{batch_id}", response_model=BatchResultResponse)
async def get_batch_status(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get the processing status of a batch.
    Frontend polls this endpoint to show progress.
    Requires authentication and enforces user isolation.

    Args:
        batch_id: Unique batch identifier
        current_user: Authenticated user from JWT token

    Returns:
        BatchResultResponse with current status and results

    Raises:
        HTTPException: If batch_id not found or access denied
    """
    # Get batch from database (with user isolation)
    batch = await get_batch(batch_id, current_user["id"])

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found or access denied")

    # Convert results from JSON strings back to DocumentResult objects
    # and add document IDs by looking them up from the database
    results = []
    if batch.get("results"):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            for result_dict in batch["results"]:
                # Look up document ID by filename and batch_id
                filename = result_dict.get('filename')

                cursor.execute('''
                    SELECT id FROM document_metadata
                    WHERE filename = ? AND batch_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (filename, batch_id))

                doc_row = cursor.fetchone()
                if doc_row:
                    result_dict['id'] = doc_row['id']

                results.append(DocumentResult(**result_dict))
        finally:
            conn.close()

    return BatchResultResponse(
        batch_id=batch_id,
        status=batch["status"],
        total_files=batch["total_files"],
        processed_files=batch["processed_files"],
        successful=batch.get("successful", 0),
        failed=batch.get("failed", 0),
        results=results,
        processing_summary=batch.get("processing_summary", {}),
        download_url=batch.get("download_url")
    )


@router.get("/download/{batch_id}")
async def download_results(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Download the organized documents as a ZIP file.
    Requires authentication and enforces user isolation.

    Args:
        batch_id: Unique batch identifier
        current_user: Authenticated user from JWT token

    Returns:
        FileResponse with ZIP file

    Raises:
        HTTPException: If batch not found, not ready, or access denied
    """
    # Get batch from database (with user isolation)
    batch = await get_batch(batch_id, current_user["id"])

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found or access denied")

    if batch["status"] != "completed":
        raise HTTPException(status_code=400, detail="Batch processing not complete")

    # Find ZIP file in processed directory
    user_processed_dir = os.path.join(settings.processed_dir, str(current_user["id"]))
    zip_candidates = [
        os.path.join(user_processed_dir, f"batch_{batch_id}.zip"),
        os.path.join(settings.processed_dir, f"batch_{batch_id}.zip"),
    ]

    zip_path = None
    for candidate in zip_candidates:
        if os.path.exists(candidate):
            zip_path = candidate
            break

    if not zip_path:
        raise HTTPException(status_code=404, detail="Results file not found")

    return FileResponse(
        path=zip_path,
        filename=f"processed_documents_{batch_id}.zip",
        media_type="application/zip"
    )


@router.get("/batches")
async def get_batches(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent batches for the current user.
    Used by the dashboard to show processing history.

    Args:
        limit: Maximum number of batches to return (default: 10)
        current_user: Authenticated user from JWT token

    Returns:
        List of recent batches with status and summary info
    """
    try:
        batches = await get_user_batches(current_user["id"], limit=limit)
        return batches
    except Exception as e:
        logger.error(f"Error fetching user batches: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch batches: {str(e)}"
        )
