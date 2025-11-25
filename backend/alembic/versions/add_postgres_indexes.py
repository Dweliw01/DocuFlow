"""Add PostgreSQL-specific performance indexes

Revision ID: pg_indexes_001
Revises: 54c6d18ecdb8
Create Date: 2025-11-25

This migration adds PostgreSQL-specific indexes for better query performance.
These indexes are skipped on SQLite as they use PostgreSQL-specific features.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'pg_indexes_001'
down_revision: Union[str, None] = '54c6d18ecdb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def is_postgresql():
    """Check if we're running on PostgreSQL."""
    bind = op.get_bind()
    return bind.dialect.name == 'postgresql'


def upgrade() -> None:
    """Add PostgreSQL-specific indexes for performance optimization."""

    if not is_postgresql():
        print("Skipping PostgreSQL-specific indexes (running on SQLite)")
        return

    # ==========================================================================
    # ORGANIZATIONS TABLE
    # ==========================================================================

    # Partial index for active organizations (most common query)
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_organizations_active
        ON organizations (id, name)
        WHERE status = 'active'
    """))

    # ==========================================================================
    # USERS TABLE
    # ==========================================================================

    # Composite index for organization lookups with email
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_users_org_email
        ON users (organization_id, email)
    """))

    # Partial index for users with organizations
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_users_with_org
        ON users (organization_id)
        WHERE organization_id IS NOT NULL
    """))

    # ==========================================================================
    # BATCHES TABLE
    # ==========================================================================

    # Composite index for user's recent batches
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_batches_user_recent
        ON batches (user_id, created_at DESC)
    """))

    # Partial index for processing batches (real-time status)
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_batches_processing
        ON batches (id, user_id, organization_id)
        WHERE status = 'processing'
    """))

    # Partial index for completed batches
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_batches_completed
        ON batches (organization_id, completed_at DESC)
        WHERE status = 'completed'
    """))

    # ==========================================================================
    # DOCUMENT_METADATA TABLE
    # ==========================================================================

    # Composite index for organization document queries
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_docs_org_status_date
        ON document_metadata (organization_id, status, processed_at DESC)
    """))

    # Partial index for pending review documents
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_docs_pending_review
        ON document_metadata (organization_id, processed_at)
        WHERE status = 'pending_review'
    """))

    # Partial index for approved documents ready for upload
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_docs_ready_upload
        ON document_metadata (organization_id, connector_type)
        WHERE status = 'approved' AND uploaded_to_connector = false
    """))

    # Index for batch document lookups
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_docs_batch_lookup
        ON document_metadata (batch_id, status)
        WHERE batch_id IS NOT NULL
    """))

    # ==========================================================================
    # USAGE_LOGS TABLE
    # ==========================================================================

    # Composite index for billing queries
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_usage_billing
        ON usage_logs (organization_id, billing_period, action_type)
    """))

    # Partial index for unbilled usage
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_usage_unbilled
        ON usage_logs (organization_id, billing_period)
        WHERE billed = false
    """))

    # Index for time-based usage queries
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_usage_timestamp
        ON usage_logs (organization_id, timestamp DESC)
    """))

    # ==========================================================================
    # ORGANIZATION_SETTINGS TABLE
    # ==========================================================================

    # Composite index for active connector lookups
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_org_settings_active
        ON organization_settings (organization_id, connector_type)
        WHERE is_active = true
    """))

    # ==========================================================================
    # CONNECTOR_CONFIGS TABLE
    # ==========================================================================

    # Composite index for user's active connectors
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_connector_user_active
        ON connector_configs (user_id, connector_type)
        WHERE is_active = true
    """))

    # ==========================================================================
    # FIELD_CORRECTIONS TABLE
    # ==========================================================================

    # Composite index for AI learning queries
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_corrections_learning
        ON field_corrections (organization_id, field_name, created_at DESC)
    """))

    # Index for document correction lookups
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_corrections_doc
        ON field_corrections (document_id, field_name)
    """))

    # ==========================================================================
    # SUBSCRIPTIONS TABLE
    # ==========================================================================

    # Partial index for active subscriptions
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_subscriptions_active
        ON subscriptions (organization_id)
        WHERE status = 'active'
    """))

    # Index for Stripe lookups
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe
        ON subscriptions (stripe_customer_id)
        WHERE stripe_customer_id IS NOT NULL
    """))

    print("PostgreSQL-specific indexes created successfully")


def downgrade() -> None:
    """Remove PostgreSQL-specific indexes."""

    if not is_postgresql():
        print("Skipping PostgreSQL index removal (running on SQLite)")
        return

    # Drop all custom indexes
    indexes_to_drop = [
        # Organizations
        'idx_organizations_active',
        # Users
        'idx_users_org_email',
        'idx_users_with_org',
        # Batches
        'idx_batches_user_recent',
        'idx_batches_processing',
        'idx_batches_completed',
        # Document metadata
        'idx_docs_org_status_date',
        'idx_docs_pending_review',
        'idx_docs_ready_upload',
        'idx_docs_batch_lookup',
        # Usage logs
        'idx_usage_billing',
        'idx_usage_unbilled',
        'idx_usage_timestamp',
        # Organization settings
        'idx_org_settings_active',
        # Connector configs
        'idx_connector_user_active',
        # Field corrections
        'idx_corrections_learning',
        'idx_corrections_doc',
        # Subscriptions
        'idx_subscriptions_active',
        'idx_subscriptions_stripe',
    ]

    for index_name in indexes_to_drop:
        op.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

    print("PostgreSQL-specific indexes removed")
