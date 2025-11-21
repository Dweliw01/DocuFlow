"""
Organization management routes for DocuFlow.
Handles organization CRUD, user management, and usage tracking.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from models import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationWithUsers,
    Subscription,
    UsageStats
)
from auth import get_current_user
from database import (
    create_organization,
    get_organization,
    update_organization,
    get_organization_users,
    update_user_organization,
    create_subscription,
    get_subscription,
    get_usage_stats,
    log_usage
)
from plan_config import (
    get_plan_config,
    calculate_trial_end_date,
    is_trial_expired,
    get_usage_warning,
    calculate_cost
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("/current")
async def get_current_organization(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current user's organization.
    Returns organization details with user list and subscription.

    Args:
        current_user: Current authenticated user (dependency)

    Returns:
        Organization with users and subscription

    Raises:
        HTTPException: If user has no organization
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization. Please complete onboarding."
        )

    org_id = current_user["organization_id"]

    # Get organization
    organization = await get_organization(org_id)
    if not organization:
        raise HTTPException(
            status_code=404,
            detail=f"Organization {org_id} not found"
        )

    # Get users in organization
    users = await get_organization_users(org_id)

    # Get subscription
    subscription = await get_subscription(org_id)

    return {
        "organization": organization,
        "users": users,
        "subscription": subscription
    }


@router.post("/create", response_model=Organization)
async def create_new_organization(
    org_data: OrganizationCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a new organization (onboarding).
    This is called when a new user completes onboarding.
    The user becomes the owner of the organization.

    Args:
        org_data: Organization creation data
        current_user: Current authenticated user (dependency)

    Returns:
        Created organization

    Raises:
        HTTPException: If user already has an organization
    """
    # Check if user already has an organization
    if current_user.get("organization_id"):
        raise HTTPException(
            status_code=400,
            detail="User already belongs to an organization"
        )

    try:
        # Create organization
        org_id = await create_organization(
            name=org_data.name,
            billing_email=org_data.billing_email,
            subscription_plan=org_data.subscription_plan or "trial"
        )

        logger.info(f"Created organization {org_id}: {org_data.name}")

        # Assign user to organization as owner
        await update_user_organization(
            user_id=current_user["id"],
            org_id=org_id,
            role="owner"
        )

        logger.info(f"Assigned user {current_user['id']} as owner of organization {org_id}")

        # Get plan configuration
        plan_name = org_data.subscription_plan or "trial"
        try:
            plan_config = get_plan_config(plan_name)
        except ValueError:
            # Fallback to trial if plan not found
            logger.warning(f"Unknown plan '{plan_name}', defaulting to trial")
            plan_name = "trial"
            plan_config = get_plan_config(plan_name)

        # Calculate trial end date if applicable
        trial_end_date = None
        if plan_config.get("is_trial"):
            trial_end_date = calculate_trial_end_date(plan_name)

        # Create subscription with plan-specific settings
        await create_subscription(
            org_id=org_id,
            plan_type=plan_name,
            price_per_document=plan_config.get("price_per_document", 0.0),
            monthly_base_fee=plan_config.get("monthly_base_fee"),
            monthly_document_limit=plan_config.get("monthly_document_limit"),
            overage_price_per_document=plan_config.get("price_per_document"),
            trial_end_date=trial_end_date
        )

        logger.info(f"Created {plan_name} subscription for organization {org_id}" +
                   (f" (expires: {trial_end_date})" if trial_end_date else ""))

        # Log onboarding completion
        await log_usage(
            org_id=org_id,
            action_type="onboarding_completed",
            document_count=0,
            user_id=current_user["id"],
            metadata={
                "organization_name": org_data.name,
                "subscription_plan": org_data.subscription_plan
            }
        )

        # Get and return the created organization
        organization = await get_organization(org_id)
        return organization

    except Exception as e:
        logger.error(f"Error creating organization: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create organization: {str(e)}"
        )


@router.patch("/current", response_model=Organization)
async def update_current_organization(
    org_data: OrganizationUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update current organization details.
    Requires owner or admin role.

    Args:
        org_data: Organization update data
        current_user: Current authenticated user (dependency)

    Returns:
        Updated organization

    Raises:
        HTTPException: If user lacks permissions or has no organization
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    # Check role (only owner/admin can update)
    if current_user.get("role") not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only organization owners and admins can update organization details"
        )

    org_id = current_user["organization_id"]

    try:
        # Update organization
        await update_organization(
            org_id=org_id,
            name=org_data.name,
            billing_email=org_data.billing_email,
            metadata=org_data.metadata
        )

        logger.info(f"Updated organization {org_id} by user {current_user['id']}")

        # Get and return updated organization
        organization = await get_organization(org_id)
        return organization

    except Exception as e:
        logger.error(f"Error updating organization: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update organization: {str(e)}"
        )


@router.get("/users")
async def list_organization_users(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    List all users in the current organization.

    Args:
        current_user: Current authenticated user (dependency)

    Returns:
        List of users

    Raises:
        HTTPException: If user has no organization
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    org_id = current_user["organization_id"]
    users = await get_organization_users(org_id)

    return {
        "organization_id": org_id,
        "users": users
    }


@router.get("/usage", response_model=UsageStats)
async def get_organization_usage(
    billing_period: str = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get usage statistics for current organization.

    Args:
        billing_period: Billing period (YYYY-MM) or None for current month
        current_user: Current authenticated user (dependency)

    Returns:
        Usage statistics

    Raises:
        HTTPException: If user has no organization
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    org_id = current_user["organization_id"]

    try:
        stats = await get_usage_stats(org_id, billing_period)

        # Calculate cost based on subscription
        subscription = await get_subscription(org_id)
        if subscription and subscription.get("plan_type") == "per_document":
            price_per_doc = subscription.get("price_per_document", 0.10)
            stats["total_cost"] = stats["total_documents_processed"] * price_per_doc

        # Add billing period to response
        if not billing_period:
            from datetime import datetime
            billing_period = datetime.utcnow().strftime("%Y-%m")
        stats["billing_period"] = billing_period

        return stats

    except Exception as e:
        logger.error(f"Error fetching usage stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch usage statistics: {str(e)}"
        )


@router.get("/subscription", response_model=Subscription)
async def get_organization_subscription(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get subscription for current organization.

    Args:
        current_user: Current authenticated user (dependency)

    Returns:
        Subscription details

    Raises:
        HTTPException: If user has no organization or subscription not found
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    org_id = current_user["organization_id"]
    subscription = await get_subscription(org_id)

    if not subscription:
        raise HTTPException(
            status_code=404,
            detail="Subscription not found for this organization"
        )

    return subscription


@router.get("/check-onboarding")
async def check_onboarding_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Check if user needs to complete onboarding.
    This is called by the frontend to determine if user should be redirected to onboarding.

    Args:
        current_user: Current authenticated user (dependency)

    Returns:
        Onboarding status
    """
    has_organization = current_user.get("organization_id") is not None

    return {
        "needs_onboarding": not has_organization,
        "has_organization": has_organization,
        "organization_id": current_user.get("organization_id"),
        "user_role": current_user.get("role"),
        "user_email": current_user.get("email")
    }


@router.get("/subscription-status")
async def get_subscription_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get comprehensive subscription status including plan details, usage, and warnings.
    This combines subscription, usage stats, plan config, and limit checking.

    Args:
        current_user: Current authenticated user (dependency)

    Returns:
        Subscription status with plan details, usage, limits, warnings
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    org_id = current_user["organization_id"]

    try:
        # Get subscription
        subscription = await get_subscription(org_id)
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found"
            )

        # Get plan configuration
        plan_type = subscription.get("plan_type", "trial")
        try:
            plan_config = get_plan_config(plan_type)
        except ValueError:
            plan_config = get_plan_config("trial")

        # Get usage stats for current period
        from datetime import datetime
        billing_period = datetime.utcnow().strftime("%Y-%m")
        usage_stats = await get_usage_stats(org_id, billing_period)

        # Calculate cost
        document_count = usage_stats.get("total_documents_processed", 0)
        cost_breakdown = calculate_cost(plan_type, document_count)

        # Check trial expiration
        trial_end_date = subscription.get("trial_end_date")
        is_expired = is_trial_expired(trial_end_date) if trial_end_date else False

        # Get usage warning
        warning = get_usage_warning(plan_type, document_count)

        # Calculate usage percentage
        limit = subscription.get("monthly_document_limit")
        usage_percent = 0
        if limit:
            usage_percent = min(100, int((document_count / limit) * 100))

        # Convert trial_end_date to string if it's a datetime object
        trial_end_date_str = None
        if trial_end_date:
            if isinstance(trial_end_date, str):
                trial_end_date_str = trial_end_date
            else:
                trial_end_date_str = trial_end_date.isoformat()

        return {
            "subscription": {
                "plan_type": plan_type,
                "plan_name": plan_config.get("display_name"),
                "status": "expired" if is_expired else subscription.get("status", "active"),
                "is_trial": plan_config.get("is_trial", False),
                "trial_end_date": trial_end_date_str,
                "is_expired": is_expired,
                "features": plan_config.get("features", [])
            },
            "usage": {
                "current_period": billing_period,
                "documents_processed": document_count,
                "document_limit": limit,
                "documents_remaining": (limit - document_count) if limit else None,
                "usage_percent": usage_percent,
                "is_unlimited": limit is None
            },
            "cost": cost_breakdown,
            "warning": warning
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get subscription status: {str(e)}"
        )


@router.get("/review-settings")
async def get_review_settings(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get review workflow settings for current organization.

    Args:
        current_user: Current authenticated user (dependency)

    Returns:
        Review settings (review_mode, confidence_threshold, auto_upload_enabled)

    Raises:
        HTTPException: If user has no organization
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    org_id = current_user["organization_id"]

    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT review_mode, confidence_threshold, auto_upload_enabled
                FROM organizations
                WHERE id = ?
            ''', (org_id,))

            result = cursor.fetchone()

            if not result:
                raise HTTPException(status_code=404, detail="Organization not found")

            return {
                "review_mode": result["review_mode"] or "review_all",
                "confidence_threshold": result["confidence_threshold"] or 0.90,
                "auto_upload_enabled": bool(result["auto_upload_enabled"])
            }

        finally:
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching review settings: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch review settings: {str(e)}"
        )


class ReviewSettingsUpdate(BaseModel):
    review_mode: Optional[str] = None
    confidence_threshold: Optional[float] = None


@router.patch("/review-settings")
async def update_review_settings(
    settings: ReviewSettingsUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update review workflow settings for current organization.
    Requires owner or admin role.

    Args:
        review_mode: Review mode ("review_all", "smart", "auto_upload")
        confidence_threshold: Confidence threshold for smart mode (0.0-1.0)
        current_user: Current authenticated user (dependency)

    Returns:
        Updated review settings

    Raises:
        HTTPException: If user lacks permissions or invalid values provided
    """
    if not current_user.get("organization_id"):
        raise HTTPException(
            status_code=404,
            detail="User not assigned to an organization"
        )

    # Check role (only owner/admin can update)
    if current_user.get("role") not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only organization owners and admins can update review settings"
        )

    org_id = current_user["organization_id"]

    # Validate inputs
    if settings.review_mode and settings.review_mode not in ["review_all", "smart", "auto_upload"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid review_mode. Must be 'review_all', 'smart', or 'auto_upload'"
        )

    if settings.confidence_threshold is not None:
        if not (0.0 <= settings.confidence_threshold <= 1.0):
            raise HTTPException(
                status_code=400,
                detail="confidence_threshold must be between 0.0 and 1.0"
            )

    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Build update query dynamically based on provided params
            updates = []
            params = []

            if settings.review_mode is not None:
                updates.append("review_mode = ?")
                params.append(settings.review_mode)

            if settings.confidence_threshold is not None:
                updates.append("confidence_threshold = ?")
                params.append(settings.confidence_threshold)

            if not updates:
                raise HTTPException(
                    status_code=400,
                    detail="No settings provided to update"
                )

            # Add org_id to params
            params.append(org_id)

            # Execute update
            query = f"UPDATE organizations SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()

            logger.info(
                f"Updated review settings for organization {org_id} by user {current_user['id']}: "
                f"review_mode={settings.review_mode}, confidence_threshold={settings.confidence_threshold}"
            )

            # Get and return updated settings
            cursor.execute('''
                SELECT review_mode, confidence_threshold, auto_upload_enabled
                FROM organizations
                WHERE id = ?
            ''', (org_id,))

            result = cursor.fetchone()

            return {
                "review_mode": result["review_mode"] or "review_all",
                "confidence_threshold": result["confidence_threshold"] or 0.90,
                "auto_upload_enabled": bool(result["auto_upload_enabled"]),
                "success": True
            }

        finally:
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating review settings: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update review settings: {str(e)}"
        )
