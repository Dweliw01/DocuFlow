"""
Database connection and schema management for DocuFlow.
Uses SQLite for MVP with async support via aiosqlite.
"""
import sqlite3
try:
    import aiosqlite
except ImportError:
    aiosqlite = None  # Allow synchronous operations if aiosqlite not installed
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Database file path
DB_PATH = Path(__file__).parent.parent / "docuflow.db"


def get_db_connection():
    """
    Get a synchronous SQLite database connection.
    Used for non-async code paths like the review workflow.

    Returns:
        sqlite3.Connection: Database connection with row factory enabled
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)  # 30 second timeout
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


async def init_database():
    """
    Initialize database and create tables if they don't exist.
    This is called on application startup.
    Includes both original tables and multi-tenant organization tables.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")

        # ====================================================================
        # ORGANIZATIONS TABLE
        # ====================================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subscription_plan TEXT DEFAULT 'trial',
                billing_email TEXT,
                status TEXT DEFAULT 'active',
                metadata TEXT,
                review_mode TEXT DEFAULT 'review_all',
                confidence_threshold REAL DEFAULT 0.85,
                auto_upload_enabled BOOLEAN DEFAULT 0
            )
        """)

        # ====================================================================
        # USERS TABLE (with organization support)
        # ====================================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auth0_user_id VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255),
                organization_id INTEGER,
                role VARCHAR(20) DEFAULT 'member',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
            )
        """)

        # ====================================================================
        # BATCHES TABLE (with organization support)
        # ====================================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                id VARCHAR(36) PRIMARY KEY,
                user_id INTEGER NOT NULL,
                organization_id INTEGER,
                status VARCHAR(20) NOT NULL,
                total_files INTEGER NOT NULL,
                processed_files INTEGER DEFAULT 0,
                successful INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                results_json TEXT,
                processing_summary_json TEXT,
                download_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
            )
        """)

        # ====================================================================
        # ORGANIZATION SETTINGS TABLE
        # ====================================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS organization_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                connector_type TEXT NOT NULL,
                config_encrypted TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                review_mode TEXT DEFAULT 'review_all',
                confidence_threshold REAL DEFAULT 0.85,
                auto_upload_enabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by_user_id INTEGER,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE(organization_id, connector_type)
            )
        """)

        # ====================================================================
        # USAGE LOGS TABLE
        # ====================================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                user_id INTEGER,
                action_type TEXT NOT NULL,
                document_count INTEGER DEFAULT 1,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                billed BOOLEAN DEFAULT FALSE,
                billing_period TEXT,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # ====================================================================
        # SUBSCRIPTIONS TABLE
        # ====================================================================
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER UNIQUE NOT NULL,
                plan_type TEXT DEFAULT 'per_document',
                price_per_document REAL DEFAULT 0.10,
                monthly_base_fee REAL,
                monthly_document_limit INTEGER,
                overage_price_per_document REAL,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                billing_cycle_start DATE,
                current_period_start DATE,
                current_period_end DATE,
                trial_end_date TIMESTAMP,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
            )
        """)

        # ====================================================================
        # LEGACY TABLES (for backward compatibility)
        # ====================================================================

        # Connector configurations table (legacy - being phased out)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS connector_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                connector_type VARCHAR(20) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                config_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Field mappings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS field_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connector_config_id INTEGER NOT NULL,
                source_field VARCHAR(255) NOT NULL,
                target_field VARCHAR(255) NOT NULL,
                confidence_score REAL,
                is_manual_override BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (connector_config_id) REFERENCES connector_configs(id),
                UNIQUE(connector_config_id, source_field)
            )
        """)

        # Document metadata table (for review workflow)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS document_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                batch_id VARCHAR(36),
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                category TEXT NOT NULL,
                extracted_data TEXT,
                status TEXT DEFAULT 'pending_review',
                confidence_score REAL,
                connector_type TEXT,
                connector_config_snapshot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                reviewed_by_user_id INTEGER,
                approved_at TIMESTAMP,
                uploaded_at TIMESTAMP,
                uploaded_to_connector BOOLEAN DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # Field corrections table (for AI learning)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS field_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                original_value TEXT,
                corrected_value TEXT NOT NULL,
                original_confidence REAL,
                correction_method TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES document_metadata(id) ON DELETE CASCADE
            )
        """)

        # ====================================================================
        # INDEXES
        # ====================================================================

        # Organization indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_organizations_created_at ON organizations(created_at)")

        # User indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_auth0_id ON users(auth0_user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(organization_id)")

        # Batch indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_batches_user_id ON batches(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_batches_org_id ON batches(organization_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_batches_created_at ON batches(created_at)")

        # Organization settings indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_org_settings_org_id ON organization_settings(organization_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_org_settings_connector_type ON organization_settings(connector_type)")

        # Usage logs indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_org_id ON usage_logs(organization_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_timestamp ON usage_logs(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_billing_period ON usage_logs(billing_period)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_billed ON usage_logs(billed)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_action_type ON usage_logs(action_type)")

        # Subscription indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_org_id ON subscriptions(organization_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer_id ON subscriptions(stripe_customer_id)")

        # Legacy indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_connector_configs_user_id ON connector_configs(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_connector_configs_type ON connector_configs(connector_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_field_mappings_config_id ON field_mappings(connector_config_id)")

        # Document metadata indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_document_metadata_org_id ON document_metadata(organization_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_document_metadata_batch_id ON document_metadata(batch_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_document_metadata_status ON document_metadata(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_document_metadata_processed_at ON document_metadata(processed_at)")

        # Field corrections indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_corrections_doc ON field_corrections(document_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_corrections_org ON field_corrections(organization_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_corrections_field ON field_corrections(field_name)")

        await db.commit()
        logger.info("Database initialized successfully with multi-tenant support")


async def get_db() -> Any:
    """Get database connection."""
    if aiosqlite is None:
        raise RuntimeError("aiosqlite is not installed. Please install it to use async database operations.")
    db = await aiosqlite.connect(DB_PATH, timeout=30.0)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode=WAL")
    return db


# ============================================================================
# User Management Functions
# ============================================================================

async def create_user(auth0_user_id: str, email: str, name: Optional[str] = None) -> int:
    """
    Create a new user in the database.

    Args:
        auth0_user_id: Auth0 user ID (e.g., "auth0|123456")
        email: User email
        name: User display name

    Returns:
        User ID
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO users (auth0_user_id, email, name, last_login) VALUES (?, ?, ?, ?)",
            (auth0_user_id, email, name, datetime.utcnow().isoformat())
        )
        await db.commit()
        user_id = cursor.lastrowid
        logger.info(f"Created user {user_id} for {email}")
        return user_id
    finally:
        await db.close()


async def get_user_by_auth0_id(auth0_user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user by Auth0 user ID.

    Args:
        auth0_user_id: Auth0 user ID

    Returns:
        User dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE auth0_user_id = ?",
            (auth0_user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by database ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email address."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def update_last_login(user_id: int):
    """Update user's last login timestamp."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), user_id)
        )
        await db.commit()
    finally:
        await db.close()


# ============================================================================
# Batch Management Functions
# ============================================================================

async def create_batch(batch_id: str, user_id: int, total_files: int) -> None:
    """
    Create a new batch record.

    Args:
        batch_id: Unique batch ID (UUID)
        user_id: User who created the batch
        total_files: Number of files in the batch
    """
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO batches (id, user_id, status, total_files) VALUES (?, ?, ?, ?)",
            (batch_id, user_id, "processing", total_files)
        )
        await db.commit()
        logger.info(f"Created batch {batch_id} for user {user_id}")
    finally:
        await db.close()


async def update_batch(
    batch_id: str,
    status: str,
    processed_files: int,
    successful: int,
    failed: int,
    results: Optional[List[Dict]] = None,
    processing_summary: Optional[Dict] = None,
    download_url: Optional[str] = None
) -> None:
    """
    Update batch with processing results.

    Args:
        batch_id: Batch ID
        status: New status (processing, completed, failed)
        processed_files: Number of processed files
        successful: Number of successful files
        failed: Number of failed files
        results: List of DocumentResult dicts
        processing_summary: Category summary dict
        download_url: URL for downloading results
    """
    db = await get_db()
    try:
        results_json = json.dumps(results) if results else None
        summary_json = json.dumps(processing_summary) if processing_summary else None
        completed_at = datetime.utcnow().isoformat() if status == "completed" else None

        await db.execute(
            """UPDATE batches
               SET status = ?, processed_files = ?, successful = ?, failed = ?,
                   results_json = ?, processing_summary_json = ?, download_url = ?,
                   completed_at = ?
               WHERE id = ?""",
            (status, processed_files, successful, failed, results_json,
             summary_json, download_url, completed_at, batch_id)
        )
        await db.commit()
    finally:
        await db.close()


async def get_batch(batch_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get batch by ID (with user isolation).

    Args:
        batch_id: Batch ID
        user_id: User ID (for isolation)

    Returns:
        Batch dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM batches WHERE id = ? AND user_id = ?",
            (batch_id, user_id)
        )
        row = await cursor.fetchone()
        if row:
            batch = dict(row)
            # Deserialize JSON fields
            if batch['results_json']:
                batch['results'] = json.loads(batch['results_json'])
            if batch['processing_summary_json']:
                batch['processing_summary'] = json.loads(batch['processing_summary_json'])
            return batch
        return None
    finally:
        await db.close()


async def get_user_batches(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get all batches for a user.

    Args:
        user_id: User ID
        limit: Maximum number of batches to return

    Returns:
        List of batch dicts
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM batches WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        batches = []
        for row in rows:
            batch = dict(row)
            if batch['results_json']:
                batch['results'] = json.loads(batch['results_json'])
            if batch['processing_summary_json']:
                batch['processing_summary'] = json.loads(batch['processing_summary_json'])
            batches.append(batch)
        return batches
    finally:
        await db.close()


# ============================================================================
# Connector Configuration Functions
# ============================================================================

async def save_connector_config(
    user_id: int,
    connector_type: str,
    config_data: Dict[str, Any]
) -> int:
    """
    Save or update connector configuration for a user.

    Args:
        user_id: User ID
        connector_type: Type of connector (docuware, google_drive, onedrive)
        config_data: Configuration dict

    Returns:
        Config ID
    """
    db = await get_db()
    try:
        # Get user's organization_id
        cursor = await db.execute(
            "SELECT organization_id FROM users WHERE id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row or not row[0]:
            raise ValueError(f"User {user_id} has no organization")
        organization_id = row[0]

        # Deactivate ALL existing active connectors for this user (only one connector active at a time)
        await db.execute(
            "UPDATE connector_configs SET is_active = FALSE WHERE user_id = ?",
            (user_id,)
        )
        logger.debug(f"Deactivated all existing connectors for user {user_id}")

        # Insert new config to connector_configs (user-level, for backward compatibility)
        config_json = json.dumps(config_data)
        cursor = await db.execute(
            """INSERT INTO connector_configs
               (user_id, connector_type, config_json, is_active, updated_at)
               VALUES (?, ?, ?, TRUE, ?)""",
            (user_id, connector_type, config_json, datetime.utcnow().isoformat())
        )
        config_id = cursor.lastrowid

        # ALSO save to organization_settings (organization-level, for upload service)
        # First, delete existing config for this organization + connector type
        await db.execute(
            """DELETE FROM organization_settings
               WHERE organization_id = ? AND connector_type = ?""",
            (organization_id, connector_type)
        )

        # Then insert the new config
        await db.execute(
            """INSERT INTO organization_settings
               (organization_id, connector_type, config_encrypted, is_active, created_by_user_id)
               VALUES (?, ?, ?, 1, ?)""",
            (organization_id, connector_type, config_json, user_id)
        )

        await db.commit()
        logger.info(f"Saved {connector_type} config {config_id} for user {user_id} and organization {organization_id} (set as active connector)")
        return config_id
    finally:
        await db.close()


async def get_active_connector_config(
    user_id: int,
    connector_type: str
) -> Optional[Dict[str, Any]]:
    """
    Get active connector configuration for a user.

    Args:
        user_id: User ID
        connector_type: Type of connector

    Returns:
        Config dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, config_json FROM connector_configs
               WHERE user_id = ? AND connector_type = ? AND is_active = TRUE""",
            (user_id, connector_type)
        )
        row = await cursor.fetchone()
        if row:
            config = json.loads(row[1])
            config['_config_id'] = row[0]  # Include config ID for field mappings
            return config
        return None
    finally:
        await db.close()


async def update_connector_last_used(config_id: int):
    """Update connector config last used timestamp."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE connector_configs SET last_used_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), config_id)
        )
        await db.commit()
    finally:
        await db.close()


async def delete_connector_config(user_id: int, connector_type: str):
    """Delete connector configuration for a user and their organization."""
    db = await get_db()
    try:
        # Get user's organization
        cursor = await db.execute(
            "SELECT organization_id FROM users WHERE id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        organization_id = row[0] if row else None

        # Delete from connector_configs (user-level)
        await db.execute(
            "DELETE FROM connector_configs WHERE user_id = ? AND connector_type = ?",
            (user_id, connector_type)
        )

        # Delete from organization_settings (org-level)
        if organization_id:
            await db.execute(
                "DELETE FROM organization_settings WHERE organization_id = ? AND connector_type = ?",
                (organization_id, connector_type)
            )

        await db.commit()
        logger.info(f"Deleted {connector_type} config for user {user_id} and organization {organization_id}")
    finally:
        await db.close()


# ============================================================================
# Field Mapping Functions
# ============================================================================

async def save_field_mapping(
    config_id: int,
    source_field: str,
    target_field: str,
    confidence: float,
    is_manual: bool = False
):
    """
    Save field mapping for a connector config.

    Args:
        config_id: Connector config ID
        source_field: Source field name (e.g., "vendor")
        target_field: Target field name (e.g., "VENDOR_NAME")
        confidence: Confidence score (0.0 - 1.0)
        is_manual: Whether user manually set this mapping
    """
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO field_mappings
               (connector_config_id, source_field, target_field, confidence_score, is_manual_override)
               VALUES (?, ?, ?, ?, ?)""",
            (config_id, source_field, target_field, confidence, is_manual)
        )
        await db.commit()
    finally:
        await db.close()


async def get_field_mappings(config_id: int) -> Dict[str, str]:
    """
    Get all field mappings for a connector config.

    Args:
        config_id: Connector config ID

    Returns:
        Dict mapping source fields to target fields
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT source_field, target_field FROM field_mappings WHERE connector_config_id = ?",
            (config_id,)
        )
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        await db.close()


async def delete_field_mappings(config_id: int):
    """Delete all field mappings for a connector config."""
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM field_mappings WHERE connector_config_id = ?",
            (config_id,)
        )
        await db.commit()
    finally:
        await db.close()


# ============================================================================
# Organization Management Functions
# ============================================================================

async def create_organization(
    name: str,
    billing_email: str,
    subscription_plan: str = "trial",
    status: str = "active",
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    """
    Create a new organization.

    Args:
        name: Organization name
        billing_email: Email for billing
        subscription_plan: Plan type (trial/starter/pro/enterprise/custom)
        status: Organization status (active/suspended/trial/cancelled)
        metadata: Optional metadata dict

    Returns:
        Organization ID
    """
    db = await get_db()
    try:
        metadata_json = json.dumps(metadata) if metadata else None
        cursor = await db.execute(
            """INSERT INTO organizations
               (name, billing_email, subscription_plan, status, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (name, billing_email, subscription_plan, status, metadata_json)
        )
        await db.commit()
        org_id = cursor.lastrowid
        logger.info(f"Created organization {org_id}: {name}")
        return org_id
    finally:
        await db.close()


async def get_organization(org_id: int) -> Optional[Dict[str, Any]]:
    """
    Get organization by ID.

    Args:
        org_id: Organization ID

    Returns:
        Organization dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM organizations WHERE id = ?",
            (org_id,)
        )
        row = await cursor.fetchone()
        if row:
            org = dict(row)
            if org.get('metadata'):
                org['metadata'] = json.loads(org['metadata'])
            return org
        return None
    finally:
        await db.close()


async def get_organization_by_user(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get organization for a user.

    Args:
        user_id: User ID

    Returns:
        Organization dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT o.* FROM organizations o
               JOIN users u ON u.organization_id = o.id
               WHERE u.id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            org = dict(row)
            if org.get('metadata'):
                org['metadata'] = json.loads(org['metadata'])
            return org
        return None
    finally:
        await db.close()


async def update_organization(
    org_id: int,
    name: Optional[str] = None,
    billing_email: Optional[str] = None,
    subscription_plan: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Update organization details.

    Args:
        org_id: Organization ID
        name: New name (optional)
        billing_email: New billing email (optional)
        subscription_plan: New plan (optional)
        status: New status (optional)
        metadata: New metadata (optional)

    Returns:
        True if updated successfully
    """
    db = await get_db()
    try:
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if billing_email is not None:
            updates.append("billing_email = ?")
            params.append(billing_email)
        if subscription_plan is not None:
            updates.append("subscription_plan = ?")
            params.append(subscription_plan)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return False

        params.append(org_id)
        query = f"UPDATE organizations SET {', '.join(updates)} WHERE id = ?"

        await db.execute(query, params)
        await db.commit()
        logger.info(f"Updated organization {org_id}")
        return True
    finally:
        await db.close()


async def get_organization_users(org_id: int) -> List[Dict[str, Any]]:
    """
    Get all users in an organization.

    Args:
        org_id: Organization ID

    Returns:
        List of user dicts
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE organization_id = ? ORDER BY created_at",
            (org_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def update_user_organization(user_id: int, org_id: int, role: str = "member"):
    """
    Update user's organization and role.

    Args:
        user_id: User ID
        org_id: Organization ID
        role: User role (owner/admin/member)
    """
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET organization_id = ?, role = ? WHERE id = ?",
            (org_id, role, user_id)
        )
        await db.commit()
        logger.info(f"Updated user {user_id} to organization {org_id} with role {role}")
    finally:
        await db.close()


# ============================================================================
# Organization Settings Functions
# ============================================================================

async def save_organization_setting(
    org_id: int,
    connector_type: str,
    config_encrypted: str,
    user_id: Optional[int] = None
) -> int:
    """
    Save or update organization-level connector setting.

    Args:
        org_id: Organization ID
        connector_type: Connector type (docuware/google_drive)
        config_encrypted: Encrypted configuration JSON
        user_id: User who created/updated the setting

    Returns:
        Setting ID
    """
    db = await get_db()
    try:
        # Check if setting already exists
        cursor = await db.execute(
            "SELECT id FROM organization_settings WHERE organization_id = ? AND connector_type = ?",
            (org_id, connector_type)
        )
        existing = await cursor.fetchone()

        if existing:
            # Update existing
            await db.execute(
                """UPDATE organization_settings
                   SET config_encrypted = ?, updated_at = ?, is_active = TRUE
                   WHERE organization_id = ? AND connector_type = ?""",
                (config_encrypted, datetime.utcnow().isoformat(), org_id, connector_type)
            )
            setting_id = existing[0]
            logger.info(f"Updated {connector_type} setting for organization {org_id}")
        else:
            # Insert new
            cursor = await db.execute(
                """INSERT INTO organization_settings
                   (organization_id, connector_type, config_encrypted, created_by_user_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (org_id, connector_type, config_encrypted, user_id, datetime.utcnow().isoformat())
            )
            setting_id = cursor.lastrowid
            logger.info(f"Created {connector_type} setting for organization {org_id}")

        await db.commit()
        return setting_id
    finally:
        await db.close()


async def get_organization_setting(org_id: int, connector_type: str) -> Optional[Dict[str, Any]]:
    """
    Get active organization setting for a connector type.

    Args:
        org_id: Organization ID
        connector_type: Connector type

    Returns:
        Setting dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM organization_settings
               WHERE organization_id = ? AND connector_type = ? AND is_active = TRUE""",
            (org_id, connector_type)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def delete_organization_setting(org_id: int, connector_type: str):
    """Delete organization setting."""
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM organization_settings WHERE organization_id = ? AND connector_type = ?",
            (org_id, connector_type)
        )
        await db.commit()
        logger.info(f"Deleted {connector_type} setting for organization {org_id}")
    finally:
        await db.close()


# ============================================================================
# Usage Logging Functions
# ============================================================================

async def log_usage(
    org_id: int,
    action_type: str,
    document_count: int = 1,
    user_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    """
    Log a usage event for billing.

    Args:
        org_id: Organization ID
        action_type: Type of action (document_upload/document_processed/ocr_extraction)
        document_count: Number of documents
        user_id: User who performed the action
        metadata: Optional metadata dict

    Returns:
        Log ID
    """
    db = await get_db()
    try:
        # Calculate billing period (YYYY-MM format)
        now = datetime.utcnow()
        billing_period = now.strftime("%Y-%m")

        metadata_json = json.dumps(metadata) if metadata else None

        cursor = await db.execute(
            """INSERT INTO usage_logs
               (organization_id, user_id, action_type, document_count, metadata, billing_period)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (org_id, user_id, action_type, document_count, metadata_json, billing_period)
        )
        await db.commit()
        log_id = cursor.lastrowid
        logger.debug(f"Logged usage for org {org_id}: {action_type} x{document_count}")
        return log_id
    finally:
        await db.close()


async def get_usage_stats(org_id: int, billing_period: Optional[str] = None) -> Dict[str, Any]:
    """
    Get aggregated usage statistics for an organization.

    Args:
        org_id: Organization ID
        billing_period: Billing period (YYYY-MM) or None for current month

    Returns:
        Usage stats dict
    """
    db = await get_db()
    try:
        if not billing_period:
            billing_period = datetime.utcnow().strftime("%Y-%m")

        # Total documents processed
        cursor = await db.execute(
            """SELECT SUM(document_count) FROM usage_logs
               WHERE organization_id = ? AND billing_period = ? AND action_type = 'document_processed'""",
            (org_id, billing_period)
        )
        total_processed = (await cursor.fetchone())[0] or 0

        # Total documents uploaded
        cursor = await db.execute(
            """SELECT SUM(document_count) FROM usage_logs
               WHERE organization_id = ? AND billing_period = ? AND action_type = 'document_upload'""",
            (org_id, billing_period)
        )
        total_uploaded = (await cursor.fetchone())[0] or 0

        # Total OCR extractions
        cursor = await db.execute(
            """SELECT SUM(document_count) FROM usage_logs
               WHERE organization_id = ? AND billing_period = ? AND action_type = 'ocr_extraction'""",
            (org_id, billing_period)
        )
        total_ocr = (await cursor.fetchone())[0] or 0

        # Calculate total documents (all types combined for billing)
        cursor = await db.execute(
            """SELECT SUM(document_count) FROM usage_logs
               WHERE organization_id = ? AND billing_period = ?""",
            (org_id, billing_period)
        )
        total_documents = (await cursor.fetchone())[0] or 0

        return {
            "organization_id": org_id,
            "billing_period": billing_period,
            "total_documents": total_documents,  # Total for billing
            "total_documents_processed": total_processed,
            "total_documents_uploaded": total_uploaded,
            "total_ocr_extractions": total_ocr,
            "total_cost": 0.0  # Will be calculated based on subscription
        }
    finally:
        await db.close()


async def get_usage_logs(
    org_id: int,
    billing_period: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get detailed usage logs for an organization.

    Args:
        org_id: Organization ID
        billing_period: Billing period (YYYY-MM) or None for all
        limit: Maximum number of logs to return

    Returns:
        List of usage log dicts
    """
    db = await get_db()
    try:
        if billing_period:
            cursor = await db.execute(
                """SELECT * FROM usage_logs
                   WHERE organization_id = ? AND billing_period = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (org_id, billing_period, limit)
            )
        else:
            cursor = await db.execute(
                """SELECT * FROM usage_logs
                   WHERE organization_id = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (org_id, limit)
            )

        rows = await cursor.fetchall()
        logs = []
        for row in rows:
            log = dict(row)
            if log.get('metadata'):
                log['metadata'] = json.loads(log['metadata'])
            logs.append(log)
        return logs
    finally:
        await db.close()


# ============================================================================
# Subscription Functions
# ============================================================================

async def create_subscription(
    org_id: int,
    plan_type: str = "per_document",
    price_per_document: float = 0.10,
    monthly_base_fee: Optional[float] = None,
    monthly_document_limit: Optional[int] = None,
    overage_price_per_document: Optional[float] = None,
    trial_end_date: Optional[datetime] = None,
    **kwargs
) -> int:
    """
    Create a subscription for an organization.

    Args:
        org_id: Organization ID
        plan_type: Plan type (per_document/tiered/custom)
        price_per_document: Price per document
        monthly_base_fee: Monthly base fee (optional)
        monthly_document_limit: Monthly document limit (optional, None = unlimited)
        overage_price_per_document: Price per document over limit (optional)
        trial_end_date: Trial expiration date (optional)
        **kwargs: Additional subscription fields

    Returns:
        Subscription ID
    """
    db = await get_db()
    try:
        from datetime import date
        today = date.today()

        cursor = await db.execute(
            """INSERT INTO subscriptions
               (organization_id, plan_type, price_per_document, monthly_base_fee,
                monthly_document_limit, overage_price_per_document, trial_end_date,
                billing_cycle_start, current_period_start, current_period_end, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (org_id, plan_type, price_per_document, monthly_base_fee,
             monthly_document_limit, overage_price_per_document, trial_end_date,
             today, today, today, 'active')
        )
        await db.commit()
        sub_id = cursor.lastrowid
        logger.info(f"Created subscription {sub_id} for organization {org_id} with plan {plan_type}")
        return sub_id
    finally:
        await db.close()


async def get_subscription(org_id: int) -> Optional[Dict[str, Any]]:
    """
    Get subscription for an organization.

    Args:
        org_id: Organization ID

    Returns:
        Subscription dict or None
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM subscriptions WHERE organization_id = ?",
            (org_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def update_subscription(
    org_id: int,
    plan_type: Optional[str] = None,
    price_per_document: Optional[float] = None,
    monthly_base_fee: Optional[float] = None,
    monthly_document_limit: Optional[int] = None,
    **kwargs
) -> bool:
    """
    Update subscription details.

    Args:
        org_id: Organization ID
        plan_type: New plan type (optional)
        price_per_document: New price per document (optional)
        monthly_base_fee: Monthly base fee for tiered plans (optional)
        monthly_document_limit: Document limit for tiered plans (optional)

    Returns:
        True if updated successfully
    """
    db = await get_db()
    try:
        updates = ["updated_at = ?"]
        params = [datetime.utcnow().isoformat()]

        if plan_type is not None:
            updates.append("plan_type = ?")
            params.append(plan_type)
        if price_per_document is not None:
            updates.append("price_per_document = ?")
            params.append(price_per_document)
        if monthly_base_fee is not None:
            updates.append("monthly_base_fee = ?")
            params.append(monthly_base_fee)
        if monthly_document_limit is not None:
            updates.append("monthly_document_limit = ?")
            params.append(monthly_document_limit)

        params.append(org_id)
        query = f"UPDATE subscriptions SET {', '.join(updates)} WHERE organization_id = ?"

        await db.execute(query, params)
        await db.commit()
        logger.info(f"Updated subscription for organization {org_id}")
        return True
    finally:
        await db.close()
