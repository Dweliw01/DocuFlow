"""
Plan configuration and tier definitions for DocuFlow.
Defines subscription plans, limits, and pricing.
"""
from datetime import datetime, timedelta
from typing import Dict, Any

# Plan tier configurations
PLAN_TIERS = {
    "trial": {
        "name": "Free Trial",
        "display_name": "Free Trial (14 Days)",
        "duration_days": 14,
        "monthly_document_limit": 50,
        "price_per_document": 0.0,
        "monthly_base_fee": 0.0,
        "features": [
            "Process up to 50 documents",
            "AI-powered categorization",
            "Basic field extraction",
            "14-day trial period"
        ],
        "is_trial": True
    },
    "starter": {
        "name": "Starter Plan",
        "display_name": "Starter",
        "duration_days": None,  # Ongoing monthly
        "monthly_document_limit": 500,
        "price_per_document": 0.10,  # Overage price
        "monthly_base_fee": 29.00,
        "features": [
            "500 documents per month",
            "AI-powered categorization",
            "Advanced field extraction",
            "Email support",
            "$0.10 per document over limit"
        ],
        "is_trial": False
    },
    "professional": {
        "name": "Professional Plan",
        "display_name": "Professional",
        "duration_days": None,
        "monthly_document_limit": 2500,
        "price_per_document": 0.08,  # Overage price
        "monthly_base_fee": 99.00,
        "features": [
            "2,500 documents per month",
            "AI-powered categorization",
            "Advanced field extraction",
            "Custom field mappings",
            "Priority support",
            "$0.08 per document over limit"
        ],
        "is_trial": False
    },
    "enterprise": {
        "name": "Enterprise Plan",
        "display_name": "Enterprise",
        "duration_days": None,
        "monthly_document_limit": 10000,
        "price_per_document": 0.05,  # Overage price
        "monthly_base_fee": 299.00,
        "features": [
            "10,000 documents per month",
            "AI-powered categorization",
            "Advanced field extraction",
            "Custom AI training",
            "Dedicated support",
            "SSO & advanced security",
            "$0.05 per document over limit"
        ],
        "is_trial": False
    }
}


def get_plan_config(plan_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific plan.

    Args:
        plan_name: Plan identifier (trial, per_document, starter, pro)

    Returns:
        Plan configuration dict

    Raises:
        ValueError: If plan not found
    """
    if plan_name not in PLAN_TIERS:
        raise ValueError(f"Unknown plan: {plan_name}")

    return PLAN_TIERS[plan_name]


def calculate_trial_end_date(plan_name: str, start_date: datetime = None) -> datetime:
    """
    Calculate trial expiration date based on plan.

    Args:
        plan_name: Plan identifier
        start_date: Trial start date (default: now)

    Returns:
        Trial end date (None if not a trial plan)
    """
    config = get_plan_config(plan_name)

    if not config.get("is_trial"):
        return None

    if start_date is None:
        start_date = datetime.utcnow()

    duration_days = config.get("duration_days")
    if duration_days:
        return start_date + timedelta(days=duration_days)

    return None


def is_trial_expired(trial_end_date) -> bool:
    """
    Check if trial has expired.

    Args:
        trial_end_date: Trial expiration date (datetime or string)

    Returns:
        True if expired, False otherwise
    """
    if trial_end_date is None:
        return False

    # Convert string to datetime if needed (SQLite returns strings)
    if isinstance(trial_end_date, str):
        try:
            # Try ISO format first
            trial_end_date = datetime.fromisoformat(trial_end_date.replace('Z', '+00:00'))
        except Exception:
            try:
                # Try parsing common datetime formats
                from datetime import datetime as dt
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']:
                    try:
                        trial_end_date = dt.strptime(trial_end_date, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return False
            except Exception:
                return False

    return datetime.utcnow() > trial_end_date


def get_usage_limit(plan_name: str) -> int:
    """
    Get document limit for a plan.

    Args:
        plan_name: Plan identifier

    Returns:
        Monthly document limit (None for unlimited)
    """
    config = get_plan_config(plan_name)
    return config.get("monthly_document_limit")


def calculate_cost(plan_name: str, document_count: int) -> Dict[str, float]:
    """
    Calculate cost for a given plan and document count.

    Args:
        plan_name: Plan identifier
        document_count: Number of documents processed

    Returns:
        Cost breakdown dict with base_fee, usage_fee, total
    """
    config = get_plan_config(plan_name)

    base_fee = config.get("monthly_base_fee", 0.0)
    limit = config.get("monthly_document_limit")
    price_per_doc = config.get("price_per_document", 0.0)

    # Calculate usage fee
    if limit is None:
        # Unlimited plan - charge for all documents
        usage_fee = document_count * price_per_doc
    elif document_count <= limit:
        # Within limit - no additional charge (except for per_document plan)
        if plan_name == "per_document":
            usage_fee = document_count * price_per_doc
        else:
            usage_fee = 0.0
    else:
        # Over limit - charge overage
        overage = document_count - limit
        usage_fee = overage * price_per_doc

    total = base_fee + usage_fee

    return {
        "base_fee": base_fee,
        "usage_fee": usage_fee,
        "total": total,
        "document_count": document_count,
        "limit": limit,
        "overage": max(0, document_count - (limit or 0)) if limit else 0
    }


def check_usage_limit(plan_name: str, current_usage: int, documents_to_add: int = 1) -> Dict[str, Any]:
    """
    Check if adding documents would exceed plan limits.

    Args:
        plan_name: Plan identifier
        current_usage: Current document count this period
        documents_to_add: Number of documents to add

    Returns:
        Dict with allowed (bool), reason (str), limit (int), current (int), would_be (int)
    """
    config = get_plan_config(plan_name)
    limit = config.get("monthly_document_limit")

    # Unlimited plans
    if limit is None:
        return {
            "allowed": True,
            "reason": "Unlimited plan",
            "limit": None,
            "current": current_usage,
            "would_be": current_usage + documents_to_add,
            "is_trial": config.get("is_trial", False)
        }

    # Plans with limits
    would_be = current_usage + documents_to_add

    if would_be > limit:
        return {
            "allowed": False,
            "reason": f"Would exceed {config['display_name']} limit of {limit} documents",
            "limit": limit,
            "current": current_usage,
            "would_be": would_be,
            "is_trial": config.get("is_trial", False)
        }

    return {
        "allowed": True,
        "reason": "Within limit",
        "limit": limit,
        "current": current_usage,
        "would_be": would_be,
        "remaining": limit - would_be,
        "is_trial": config.get("is_trial", False)
    }


def get_usage_warning(plan_name: str, current_usage: int) -> Dict[str, Any]:
    """
    Get usage warning if approaching limit.

    Args:
        plan_name: Plan identifier
        current_usage: Current document count

    Returns:
        Warning dict with show (bool), level (str), message (str)
    """
    config = get_plan_config(plan_name)
    limit = config.get("monthly_document_limit")

    if limit is None:
        return {"show": False}

    usage_percent = (current_usage / limit) * 100

    if usage_percent >= 100:
        return {
            "show": True,
            "level": "critical",
            "message": f"You've reached your {config['display_name']} limit of {limit} documents.",
            "percent": 100
        }
    elif usage_percent >= 90:
        remaining = limit - current_usage
        return {
            "show": True,
            "level": "warning",
            "message": f"You have {remaining} documents remaining in your {config['display_name']}.",
            "percent": int(usage_percent)
        }
    elif usage_percent >= 75:
        remaining = limit - current_usage
        return {
            "show": True,
            "level": "info",
            "message": f"{remaining} documents remaining this month.",
            "percent": int(usage_percent)
        }

    return {"show": False}
