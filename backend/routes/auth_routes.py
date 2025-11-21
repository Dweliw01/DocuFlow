"""
Authentication routes for DocuFlow.
Handles Auth0 configuration, user info, and logout.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import Auth0Config, User
from auth import get_current_user
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.get("/config", response_model=Auth0Config)
async def get_auth_config():
    """
    Get Auth0 configuration for frontend authentication.
    This is a public endpoint (no auth required).

    Returns:
        Auth0Config with domain, client_id, and audience

    Raises:
        HTTPException: If Auth0 is not configured
    """
    if not settings.auth0_domain or not settings.auth0_client_id:
        raise HTTPException(
            status_code=500,
            detail="Auth0 not configured. Please set AUTH0_DOMAIN and AUTH0_CLIENT_ID in .env file"
        )

    return Auth0Config(
        domain=settings.auth0_domain,
        client_id=settings.auth0_client_id,
        audience=settings.auth0_audience
    )


@router.get("/user")
async def get_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current authenticated user information.
    This endpoint requires authentication.

    Args:
        current_user: Current user from JWT token (dependency)

    Returns:
        User information
    """
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "name": current_user.get("name"),
        "auth0_user_id": current_user["auth0_user_id"],
        "created_at": current_user["created_at"],
        "last_login": current_user.get("last_login")
    }


@router.post("/logout")
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Logout current user.
    Note: JWT tokens are stateless, so this is primarily for logging purposes.
    Client should remove token from storage.

    Args:
        current_user: Current user from JWT token (dependency)

    Returns:
        Success message
    """
    logger.info(f"User {current_user['email']} logged out")

    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.get("/health")
async def auth_health_check():
    """
    Check if authentication system is properly configured.
    Public endpoint for monitoring.

    Returns:
        Health status
    """
    auth0_configured = bool(settings.auth0_domain and settings.auth0_client_id)

    return {
        "status": "healthy" if auth0_configured else "not_configured",
        "auth0_configured": auth0_configured,
        "auth0_domain": settings.auth0_domain if auth0_configured else None
    }
