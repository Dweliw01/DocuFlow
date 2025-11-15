"""
Configuration management for the Document Digitization MVP.
Reads environment variables from .env file and provides app-wide settings.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses pydantic-settings to validate and type-check configuration.
    """

    # API Keys
    anthropic_api_key: str
    claude_model: str = "claude-haiku-4-5"  # Claude Haiku 4.5 for better accuracy

    # OCR Settings
    use_google_vision: bool = False
    google_application_credentials: str | None = None

    # Directories
    upload_dir: str = "./storage/uploads"
    processed_dir: str = "./storage/processed"
    log_dir: str = "./storage/logs"

    # File Settings
    max_file_size: int = 50  # MB
    allowed_extensions: List[str] = ["pdf"]
    max_concurrent_processing: int = 5

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Google Drive OAuth
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://localhost:8000/api/connectors/google-drive/oauth-callback"

    # Auth0 Settings
    auth0_domain: str | None = None
    auth0_client_id: str | None = None
    auth0_client_secret: str | None = None
    auth0_audience: str = "https://docuflow-api"

    # Database
    database_url: str = "sqlite:///./docuflow.db"

    # Security
    secret_key: str = "change-this-to-random-32-char-string-in-production"
    encryption_key: str | None = None

    class Config:
        """Pydantic configuration"""
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        """
        Initialize settings and create necessary directories.
        This ensures storage folders exist when the app starts.
        """
        super().__init__(**kwargs)

        # Create directories if they don't exist
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        print(f"[OK] Configuration loaded")
        print(f"  - Upload directory: {self.upload_dir}")
        print(f"  - Processed directory: {self.processed_dir}")
        print(f"  - Using {self.claude_model} for AI categorization")
        print(f"  - Using Tesseract OCR (free)")


# Create a single settings instance to use throughout the app
settings = Settings()
