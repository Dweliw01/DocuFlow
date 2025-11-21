-- Migration 001: Add Multi-Tenant Organizations Support
-- This migration transforms DocuFlow into a multi-tenant SaaS application
--
-- Changes:
-- 1. Create organizations table
-- 2. Create organization_settings table (replaces user-level settings)
-- 3. Create usage_logs table (for billing)
-- 4. Create subscriptions table (flexible billing)
-- 5. Update users table (add organization_id and role)
-- 6. Migrate existing data to organization model

-- ============================================================================
-- 1. CREATE ORGANIZATIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subscription_plan TEXT DEFAULT 'trial',  -- trial/starter/pro/enterprise/custom
    billing_email TEXT,
    status TEXT DEFAULT 'active',  -- active/suspended/trial/cancelled
    metadata TEXT  -- JSON for flexible additional data
);

CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status);
CREATE INDEX IF NOT EXISTS idx_organizations_created_at ON organizations(created_at);


-- ============================================================================
-- 2. CREATE ORGANIZATION_SETTINGS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS organization_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    connector_type TEXT NOT NULL,  -- 'docuware' or 'google_drive'
    config_encrypted TEXT NOT NULL,  -- Encrypted JSON with credentials
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id INTEGER,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(organization_id, connector_type)
);

CREATE INDEX IF NOT EXISTS idx_org_settings_org_id ON organization_settings(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_settings_connector_type ON organization_settings(connector_type);


-- ============================================================================
-- 3. CREATE USAGE_LOGS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    user_id INTEGER,
    action_type TEXT NOT NULL,  -- 'document_upload', 'document_processed', 'ocr_extraction', etc.
    document_count INTEGER DEFAULT 1,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,  -- JSON: file sizes, categories, processing time, etc.
    billed BOOLEAN DEFAULT FALSE,  -- Whether this has been invoiced
    billing_period TEXT,  -- e.g., '2025-01' for January 2025
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_org_id ON usage_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_timestamp ON usage_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_usage_logs_billing_period ON usage_logs(billing_period);
CREATE INDEX IF NOT EXISTS idx_usage_logs_billed ON usage_logs(billed);
CREATE INDEX IF NOT EXISTS idx_usage_logs_action_type ON usage_logs(action_type);


-- ============================================================================
-- 4. CREATE SUBSCRIPTIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER UNIQUE NOT NULL,
    plan_type TEXT DEFAULT 'per_document',  -- per_document/tiered/custom

    -- For per-document billing
    price_per_document REAL DEFAULT 0.10,  -- e.g., 0.10 for $0.10/doc

    -- For tiered billing
    monthly_base_fee REAL,  -- e.g., 99.00 for $99/month
    monthly_document_limit INTEGER,  -- e.g., 1000 documents/month
    overage_price_per_document REAL,  -- Price per doc over limit

    -- Payment integration (future)
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,

    -- Billing cycle
    billing_cycle_start DATE,
    current_period_start DATE,
    current_period_end DATE,

    -- Status
    status TEXT DEFAULT 'active',  -- active/past_due/cancelled

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_org_id ON subscriptions(organization_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer_id ON subscriptions(stripe_customer_id);


-- ============================================================================
-- 5. UPDATE USERS TABLE
-- ============================================================================

-- Add organization_id column (NULL for now, will be populated in migration script)
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we check first
-- This will be handled by the Python migration script

-- Add role column (owner/admin/member)
-- This will also be handled by the Python migration script


-- ============================================================================
-- 6. UPDATE BATCHES TABLE
-- ============================================================================

-- Add organization_id to batches for multi-tenant isolation
-- This will be handled by the Python migration script to avoid conflicts


-- ============================================================================
-- NOTES
-- ============================================================================

-- Column additions to existing tables are handled by the Python migration script
-- to properly check if columns already exist and migrate data safely.
--
-- After running this SQL migration, run the Python migration script:
--   python backend/migrations/migrate_to_organizations.py
--
-- The Python script will:
-- 1. Check and add organization_id and role columns to users table
-- 2. Check and add organization_id column to batches table
-- 3. Create a default organization for each existing user
-- 4. Migrate connector_configs to organization_settings
-- 5. Set up default subscriptions for existing users
