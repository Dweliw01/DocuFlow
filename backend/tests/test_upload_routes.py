"""
Integration tests for upload routes.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path
import sys
import io
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from models import DocumentCategory, ExtractedData, LineItem


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_pdf_file():
    """Create a mock PDF file for upload."""
    content = b"%PDF-1.4\n%Test PDF content"
    return ("test_invoice.pdf", io.BytesIO(content), "application/pdf")


@pytest.fixture
def multiple_mock_pdf_files():
    """Create multiple mock PDF files for batch upload."""
    files = []
    for i in range(3):
        content = b"%PDF-1.4\n%Test PDF content " + str(i).encode()
        files.append((f"test_invoice_{i}.pdf", io.BytesIO(content), "application/pdf"))
    return files


@pytest.mark.integration
class TestUploadEndpoint:
    """Test document upload endpoint."""

    def test_upload_no_files(self, client):
        """Test upload with no files returns 422."""
        response = client.post("/api/upload", files=[])

        assert response.status_code == 422  # Unprocessable Entity

    def test_upload_non_pdf_file(self, client):
        """Test upload with non-PDF file returns error."""
        non_pdf = ("test.txt", io.BytesIO(b"Not a PDF"), "text/plain")

        response = client.post(
            "/api/upload",
            files=[("files", non_pdf)]
        )

        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    def test_upload_too_many_files(self, client):
        """Test upload with more than 100 files returns error."""
        # Create 101 fake file entries
        files = []
        for i in range(101):
            content = b"%PDF-1.4\n%Test"
            files.append(("files", (f"test_{i}.pdf", io.BytesIO(content), "application/pdf")))

        response = client.post("/api/upload", files=files)

        assert response.status_code == 400
        assert "Maximum 100 files" in response.json()["detail"]

    @patch('routes.upload.ocr_service')
    @patch('routes.upload.ai_service')
    @patch('routes.upload.file_service')
    def test_upload_single_pdf_success(
        self,
        mock_file_service,
        mock_ai_service,
        mock_ocr_service,
        client,
        mock_pdf_file
    ):
        """Test successful upload of single PDF file."""
        # Setup mocks
        mock_ocr_service.extract_text.return_value = "Test invoice text"

        mock_ai_service.categorize_document = AsyncMock(return_value=(
            DocumentCategory.INVOICE,
            0.95,
            ExtractedData(vendor="Test Vendor", amount=1000.00)
        ))

        response = client.post(
            "/api/upload",
            files=[("files", mock_pdf_file)]
        )

        assert response.status_code == 200
        data = response.json()

        assert "batch_id" in data
        assert data["status"] == "processing" or data["status"] == "completed"
        assert data["total_files"] >= 1

    @patch('routes.upload.ocr_service')
    @patch('routes.upload.ai_service')
    def test_upload_multiple_pdfs_success(
        self,
        mock_ai_service,
        mock_ocr_service,
        client,
        multiple_mock_pdf_files
    ):
        """Test successful upload of multiple PDF files."""
        mock_ocr_service.extract_text.return_value = "Test invoice text"

        mock_ai_service.categorize_document = AsyncMock(return_value=(
            DocumentCategory.INVOICE,
            0.95,
            None
        ))

        files = [("files", f) for f in multiple_mock_pdf_files]

        response = client.post("/api/upload", files=files)

        assert response.status_code == 200
        data = response.json()

        assert "batch_id" in data
        assert data["total_files"] == 3


@pytest.mark.integration
class TestStatusEndpoint:
    """Test batch status endpoint."""

    def test_status_invalid_batch_id(self, client):
        """Test status check with non-existent batch ID."""
        response = client.get("/api/status/invalid-batch-id-123")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch('routes.upload.batch_results', {"test-batch-123": {
        "status": "processing",
        "total_files": 5,
        "processed_files": 3,
        "results": []
    }})
    def test_status_batch_processing(self, client):
        """Test status check for batch in processing."""
        response = client.get("/api/status/test-batch-123")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "processing"
        assert data["total_files"] == 5
        assert data["processed_files"] == 3

    @patch('routes.upload.batch_results', {"test-batch-456": {
        "status": "completed",
        "total_files": 2,
        "processed_files": 2,
        "results": [
            {
                "filename": "test1.pdf",
                "category": "Invoice",
                "confidence": 0.95,
                "extracted_data": None,
                "upload_result": None
            },
            {
                "filename": "test2.pdf",
                "category": "Contract",
                "confidence": 0.90,
                "extracted_data": None,
                "upload_result": None
            }
        ]
    }})
    def test_status_batch_completed(self, client):
        """Test status check for completed batch."""
        response = client.get("/api/status/test-batch-456")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed"
        assert data["total_files"] == 2
        assert data["processed_files"] == 2
        assert len(data["results"]) == 2


@pytest.mark.integration
class TestDownloadEndpoint:
    """Test download endpoint."""

    def test_download_invalid_batch_id(self, client):
        """Test download with non-existent batch ID."""
        response = client.get("/api/download/invalid-batch-id-789")

        assert response.status_code == 404

    @patch('routes.upload.batch_results', {"test-batch-complete": {
        "status": "completed",
        "zip_path": "/tmp/test.zip"
    }})
    @patch('routes.upload.os.path.exists', return_value=True)
    def test_download_success(self, mock_exists, client):
        """Test successful download of completed batch."""
        with patch('routes.upload.FileResponse') as mock_file_response:
            mock_file_response.return_value = Mock()

            response = client.get("/api/download/test-batch-complete")

            # FileResponse should be called
            mock_file_response.assert_called_once()

    @patch('routes.upload.batch_results', {"test-batch-processing": {
        "status": "processing",
        "total_files": 5,
        "processed_files": 3
    }})
    def test_download_batch_not_ready(self, client):
        """Test download when batch is still processing."""
        response = client.get("/api/download/test-batch-processing")

        assert response.status_code == 400
        assert "still processing" in response.json()["detail"].lower()


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndProcessing:
    """Test end-to-end document processing flow."""

    @patch('routes.upload.ocr_service')
    @patch('routes.upload.ai_service')
    @patch('routes.upload.file_service')
    def test_full_upload_process_status_download_flow(
        self,
        mock_file_service,
        mock_ai_service,
        mock_ocr_service,
        client,
        mock_pdf_file
    ):
        """Test complete flow: upload -> status check -> download."""
        # Setup mocks
        mock_ocr_service.extract_text.return_value = "Test invoice from Acme Corp for $1,234.56"

        mock_ai_service.categorize_document = AsyncMock(return_value=(
            DocumentCategory.INVOICE,
            0.95,
            ExtractedData(
                vendor="Acme Corp",
                amount=1234.56,
                date="2024-01-15"
            )
        ))

        mock_file_service.organize_files.return_value = Path("/tmp/batch")

        # Step 1: Upload file
        upload_response = client.post(
            "/api/upload",
            files=[("files", mock_pdf_file)]
        )

        assert upload_response.status_code == 200
        batch_id = upload_response.json()["batch_id"]

        # Step 2: Check status (may need to wait for background processing)
        import time
        time.sleep(0.5)  # Give background task time to process

        status_response = client.get(f"/api/status/{batch_id}")

        assert status_response.status_code == 200
        status_data = status_response.json()

        assert status_data["batch_id"] == batch_id
        assert status_data["total_files"] >= 1


@pytest.mark.integration
class TestConnectorIntegration:
    """Test connector integration with upload flow."""

    @patch('routes.upload.connector_manager')
    @patch('routes.upload.get_current_config_with_decrypted_password')
    @patch('routes.upload.ocr_service')
    @patch('routes.upload.ai_service')
    def test_upload_with_connector_enabled(
        self,
        mock_ai_service,
        mock_ocr_service,
        mock_get_config,
        mock_connector_manager,
        client,
        mock_pdf_file,
        sample_docuware_config
    ):
        """Test upload with DocuWare connector enabled."""
        # Setup mocks
        mock_ocr_service.extract_text.return_value = "Invoice text"

        mock_ai_service.categorize_document = AsyncMock(return_value=(
            DocumentCategory.INVOICE,
            0.95,
            ExtractedData(vendor="Test", amount=100.00)
        ))

        mock_get_config.return_value = sample_docuware_config

        mock_connector_manager.upload_document = AsyncMock(return_value="doc-12345")

        response = client.post(
            "/api/upload",
            files=[("files", mock_pdf_file)]
        )

        assert response.status_code == 200

    @patch('routes.upload.connector_manager')
    @patch('routes.upload.get_current_config_with_decrypted_password')
    @patch('routes.upload.ocr_service')
    @patch('routes.upload.ai_service')
    def test_upload_connector_upload_failure(
        self,
        mock_ai_service,
        mock_ocr_service,
        mock_get_config,
        mock_connector_manager,
        client,
        mock_pdf_file,
        sample_docuware_config
    ):
        """Test upload when connector upload fails."""
        mock_ocr_service.extract_text.return_value = "Invoice text"

        mock_ai_service.categorize_document = AsyncMock(return_value=(
            DocumentCategory.INVOICE,
            0.95,
            ExtractedData(vendor="Test", amount=100.00)
        ))

        mock_get_config.return_value = sample_docuware_config

        # Simulate upload failure
        mock_connector_manager.upload_document = AsyncMock(return_value=None)

        response = client.post(
            "/api/upload",
            files=[("files", mock_pdf_file)]
        )

        # Should still succeed, just mark upload as failed
        assert response.status_code == 200


@pytest.mark.integration
class TestFileValidation:
    """Test file validation logic."""

    def test_upload_oversized_file(self, client):
        """Test upload with file exceeding size limit."""
        # Create a large fake PDF (51MB worth of data)
        large_content = b"%PDF-1.4\n" + (b"X" * (51 * 1024 * 1024))
        large_file = ("huge.pdf", io.BytesIO(large_content), "application/pdf")

        with patch('routes.upload.settings.max_file_size', 50):
            response = client.post(
                "/api/upload",
                files=[("files", large_file)]
            )

            assert response.status_code == 400
            assert "exceeds maximum" in response.json()["detail"].lower()

    def test_upload_empty_pdf(self, client):
        """Test upload with empty PDF file."""
        empty_file = ("empty.pdf", io.BytesIO(b""), "application/pdf")

        response = client.post(
            "/api/upload",
            files=[("files", empty_file)]
        )

        # Should handle gracefully (may succeed but fail processing)
        assert response.status_code in [200, 400]


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling in upload flow."""

    @patch('routes.upload.ocr_service')
    def test_upload_ocr_failure(self, mock_ocr_service, client, mock_pdf_file):
        """Test upload when OCR fails."""
        mock_ocr_service.extract_text.side_effect = Exception("OCR failed")

        response = client.post(
            "/api/upload",
            files=[("files", mock_pdf_file)]
        )

        # Should handle error gracefully
        assert response.status_code == 200

        # Check status shows error
        batch_id = response.json()["batch_id"]
        import time
        time.sleep(0.5)

        status_response = client.get(f"/api/status/{batch_id}")
        # Processing should complete despite error

    @patch('routes.upload.ocr_service')
    @patch('routes.upload.ai_service')
    def test_upload_ai_failure(
        self,
        mock_ai_service,
        mock_ocr_service,
        client,
        mock_pdf_file
    ):
        """Test upload when AI categorization fails."""
        mock_ocr_service.extract_text.return_value = "Test text"

        mock_ai_service.categorize_document = AsyncMock(
            side_effect=Exception("AI service failed")
        )

        response = client.post(
            "/api/upload",
            files=[("files", mock_pdf_file)]
        )

        # Should still return success (error handled in background)
        assert response.status_code == 200
