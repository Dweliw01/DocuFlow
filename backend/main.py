"""
Main FastAPI application entry point.
Configures the web server, middleware, and routes.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes import upload
from routes import connector_routes
from config import settings
import os
import logging
import sys

# Create FastAPI application
app = FastAPI(
    title="Document Digitization MVP",
    description="AI-powered document categorization service using Claude and Tesseract OCR",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI at /docs
    redoc_url="/redoc"  # ReDoc at /redoc
)

# CORS middleware - allows frontend to call API
# In production, replace "*" with specific frontend URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include API routes with /api prefix
app.include_router(upload.router, prefix="/api", tags=["documents"])
app.include_router(connector_routes.router, tags=["connectors"])

# Serve frontend static files (HTML, CSS, JS)
# This must come LAST to avoid overriding API routes
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    print(f"⚠ Warning: Frontend directory not found at {frontend_path}")


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint for monitoring.
    Returns service status and configuration info.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "ocr_provider": "Google Vision" if settings.use_google_vision else "Tesseract",
        "ai_provider": "Claude Haiku",
        "max_file_size_mb": settings.max_file_size,
        "max_concurrent_processing": settings.max_concurrent_processing
    }


@app.on_event("startup")
async def startup_event():
    """
    Run on application startup.
    Configure logging and print configuration info.
    """
    # Configure logging to output to console with colored formatting
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Set specific log levels for different modules
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)  # Reduce uvicorn noise
    logging.getLogger('uvicorn.error').setLevel(logging.INFO)

    # Application loggers
    logging.getLogger('backend.connectors').setLevel(logging.INFO)
    logging.getLogger('backend.services').setLevel(logging.INFO)
    logging.getLogger('backend.routes').setLevel(logging.INFO)

    print("\n" + "=" * 60)
    print("Document Digitization MVP")
    print("=" * 60)
    print(f"Server: http://{settings.host}:{settings.port}")
    print(f"API Docs: http://{settings.host}:{settings.port}/docs")
    print(f"AI: Claude Haiku")
    print(f"OCR: {'Google Vision' if settings.use_google_vision else 'Tesseract (free)'}")
    print(f"Max file size: {settings.max_file_size}MB")
    print(f"Concurrent processing: {settings.max_concurrent_processing}")
    print(f"Logging: INFO level enabled")
    print("=" * 60 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Run on application shutdown.
    Clean up resources if needed.
    """
    print("\n🛑 Shutting down Document Digitization Service...")


# Run the application (for development)
if __name__ == "__main__":
    import uvicorn

    print("Starting development server...")
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )
