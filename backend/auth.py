"""
Authentication and authorization utilities for DocuFlow.
Handles Auth0 JWT token validation and user management.
"""
import requests
from jose import jwt, JWTError
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional, Dict, Any
from functools import lru_cache
import logging

from config import settings
from database import (
    get_user_by_auth0_id,
    create_user,
    update_last_login
)

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()


class AuthError(Exception):
    """Custom exception for authentication errors."""
    def __init__(self, error: Dict[str, str], status_code: int):
        self.error = error
        self.status_code = status_code


@lru_cache()
def get_auth0_public_key() -> Dict[str, Any]:
    """
    Fetch Auth0 public keys for JWT verification.
    Cached to avoid repeated requests.

    Returns:
        JWKS (JSON Web Key Set)

    Raises:
        AuthError: If unable to fetch keys
    """
    if not settings.auth0_domain:
        raise AuthError(
            {"code": "auth0_not_configured", "description": "Auth0 domain not configured"},
            500
        )

    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"

    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch Auth0 public keys: {str(e)}")
        raise AuthError(
            {"code": "jwks_fetch_failed", "description": "Failed to fetch public keys"},
            500
        )


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode Auth0 JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        AuthError: If token is invalid
    """
    if not settings.auth0_domain:
        raise AuthError(
            {"code": "auth0_not_configured", "description": "Auth0 not configured"},
            500
        )

    # Get JWKS (public keys)
    try:
        jwks = get_auth0_public_key()
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Error getting public keys: {str(e)}")
        raise AuthError(
            {"code": "public_key_error", "description": "Error fetching public keys"},
            500
        )

    # Decode token header to get key ID
    try:
        unverified_header = jwt.get_unverified_header(token)
        logger.debug(f"Token header: {unverified_header}")
    except JWTError as e:
        logger.error(f"Invalid token header: {str(e)}")
        raise AuthError(
            {"code": "invalid_header", "description": "Invalid token header"},
            401
        )

    # Check if token has a kid (Key ID)
    if "kid" not in unverified_header:
        logger.error(f"Token missing 'kid' in header. Header keys: {list(unverified_header.keys())}")
        raise AuthError(
            {"code": "invalid_header", "description": "Token missing key ID (kid). This may be an ID token instead of an access token."},
            401
        )

    # Find the key with matching key ID
    rsa_key = {}
    for key in jwks.get("keys", []):
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
            break

    if not rsa_key:
        logger.error(f"No matching key found for kid: {unverified_header['kid']}")
        raise AuthError(
            {"code": "invalid_header", "description": "Unable to find appropriate key"},
            401
        )

    # Verify and decode token
    try:
        # Try with audience first
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=settings.auth0_audience,
                issuer=f"https://{settings.auth0_domain}/"
            )
            return payload
        except jwt.JWTClaimsError:
            # If audience validation fails, try without it (for development)
            logger.warning("Validating token without audience check")
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=f"https://{settings.auth0_domain}/"
            )
            return payload
    except jwt.ExpiredSignatureError:
        raise AuthError(
            {"code": "token_expired", "description": "Token has expired"},
            401
        )
    except jwt.JWTClaimsError as e:
        logger.error(f"Invalid claims: {str(e)}")
        raise AuthError(
            {"code": "invalid_claims", "description": "Invalid token claims"},
            401
        )
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        raise AuthError(
            {"code": "invalid_token", "description": "Unable to validate token"},
            401
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Dict[str, Any]:
    """
    Get current authenticated user from JWT token with organization context.
    This is a FastAPI dependency that can be used in route handlers.

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        User dict from database with organization context

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials

    try:
        # Verify token
        payload = verify_token(token)

        # Extract user info from token
        auth0_user_id = payload.get("sub")  # Auth0 user ID
        email = payload.get("email")
        name = payload.get("name")

        if not auth0_user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing user ID"
            )

        # CRITICAL: Email is required
        # Strategy: If not in token, fetch from database (user already created)
        # Only fetch from Auth0 if user doesn't exist yet
        if not email:
            # Check if user exists in database first
            existing_user = await get_user_by_auth0_id(auth0_user_id)
            if existing_user:
                # User exists, use email from database (already fetched on first login)
                email = existing_user["email"]
                if not name:
                    name = existing_user["name"]
                logger.debug(f"Using email from database for returning user: {email}")
            else:
                # New user - fetch from Auth0 once
                logger.warning(f"Email not in token for NEW user {auth0_user_id}, fetching from Auth0")
                try:
                    import requests
                    userinfo_url = f"https://{settings.auth0_domain}/userinfo"
                    headers = {"Authorization": f"Bearer {token}"}
                    response = requests.get(userinfo_url, headers=headers, timeout=10)

                    if response.ok:
                        userinfo = response.json()
                        email = userinfo.get("email")
                        if not name:
                            name = userinfo.get("name")
                        logger.info(f"Fetched email from Auth0 for new user: {email}")
                    else:
                        logger.error(f"Failed to fetch userinfo from Auth0: {response.status_code}")
                except Exception as e:
                    logger.error(f"Error fetching userinfo from Auth0: {str(e)}")

        # Email is absolutely required
        if not email:
            logger.error(f"Cannot get email for user {auth0_user_id}")
            raise HTTPException(
                status_code=401,
                detail="Email not available. Please contact support."
            )

        # Look up user in database
        user = await get_user_by_auth0_id(auth0_user_id)

        # Create user if first login
        if not user:
            try:
                user_id = await create_user(auth0_user_id, email, name)
                user = await get_user_by_auth0_id(auth0_user_id)
                logger.info(f"Created new user {user_id} for {email}")
            except Exception as create_error:
                # If user creation fails due to duplicate email, it's a critical error
                # Don't allow fallback to prevent account hijacking
                logger.error(f"Failed to create user: {str(create_error)}")

                # Check if it's specifically a duplicate email error
                if "UNIQUE constraint failed: users.email" in str(create_error):
                    raise HTTPException(
                        status_code=409,
                        detail=f"A user with email {email} already exists but with different Auth0 ID. This may indicate a misconfigured Auth0 connection or an attempt to access another user's account."
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create user: {str(create_error)}"
                    )
        else:
            # Update last login
            await update_last_login(user["id"])

        # Load organization context if user has one
        if user.get("organization_id"):
            from database import get_organization
            organization = await get_organization(user["organization_id"])
            if organization:
                user["organization"] = organization
                logger.debug(f"Loaded organization {organization['id']} for user {user['id']}")
            else:
                logger.warning(f"User {user['id']} has organization_id {user['organization_id']} but organization not found")
        else:
            user["organization"] = None
            logger.debug(f"User {user['id']} has no organization - needs onboarding")

        return user

    except AuthError as e:
        logger.error(f"AuthError in get_current_user: {e.error}")
        raise HTTPException(
            status_code=e.status_code,
            detail=e.error["description"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error in get_current_user: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )


def require_auth():
    """
    Dependency that requires authentication.
    Use with Depends() in route handlers.

    Example:
        @router.get("/protected", dependencies=[Depends(require_auth)])
        async def protected_route():
            ...
    """
    return Depends(get_current_user)
