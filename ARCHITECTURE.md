# DocuFlow Multi-Tenant SaaS Architecture

## Business Model

DocuFlow is a **multi-tenant SaaS application** where:
- We host the application centrally
- Small businesses sign up as customers (organizations)
- Each organization can have one or multiple users
- We track usage per organization for billing
- Customers can self-service configure their DocuWare/Google Drive integrations

## Billing Strategy

**Flexible billing model** - build infrastructure to support:
- **Per-document pricing**: Pay per document processed (initial model)
- **Tiered plans**: Monthly plans with document limits (future option)
- **Hybrid**: Base fee + overage charges (future option)

The system tracks granular usage data to support any billing model we choose.

---

## Database Schema

### New Tables

#### `organizations`
The core tenant entity - represents each customer business.

```sql
CREATE TABLE organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subscription_plan TEXT DEFAULT 'trial',  -- trial/starter/pro/enterprise/custom
    billing_email TEXT,
    status TEXT DEFAULT 'active',  -- active/suspended/trial/cancelled
    metadata TEXT  -- JSON for flexible additional data
);
```

#### `users` (UPDATE existing table)
Link users to their organization.

```sql
ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id);
ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'member';  -- owner/admin/member
```

**Roles:**
- `owner`: Created the organization, full access, billing control
- `admin`: Can manage settings and invite users
- `member`: Can use the system, limited settings access

#### `organization_settings`
Replaces user-level settings. Each organization has its own connector configurations.

```sql
CREATE TABLE organization_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    connector_type TEXT NOT NULL,  -- 'docuware' or 'google_drive'
    config_encrypted TEXT NOT NULL,  -- Encrypted JSON with credentials
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id INTEGER REFERENCES users(id),
    UNIQUE(organization_id, connector_type)
);
```

#### `usage_logs`
Granular tracking of all billable actions.

```sql
CREATE TABLE usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    user_id INTEGER REFERENCES users(id),
    action_type TEXT NOT NULL,  -- 'document_upload', 'document_processed', 'ocr_extraction', etc.
    document_count INTEGER DEFAULT 1,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,  -- JSON: file sizes, categories, processing time, etc.
    billed BOOLEAN DEFAULT FALSE,  -- Whether this has been invoiced
    billing_period TEXT  -- e.g., '2025-01' for January 2025
);
```

**Action Types:**
- `document_upload`: File uploaded
- `document_processed`: AI categorization completed
- `ocr_extraction`: OCR performed on image/PDF
- `api_call_anthropic`: Claude API usage
- `storage_used`: Storage metrics

#### `subscriptions`
Flexible billing configuration per organization.

```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER UNIQUE NOT NULL REFERENCES organizations(id),
    plan_type TEXT DEFAULT 'per_document',  -- per_document/tiered/custom

    -- For per-document billing
    price_per_document REAL,  -- e.g., 0.10 for $0.10/doc

    -- For tiered billing
    monthly_base_fee REAL,  -- e.g., 99.00 for $99/month
    monthly_document_limit INTEGER,  -- e.g., 1000 documents/month
    overage_price_per_document REAL,  -- Price per doc over limit

    -- Payment integration
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,

    -- Billing cycle
    billing_cycle_start DATE,
    current_period_start DATE,
    current_period_end DATE,

    -- Status
    status TEXT DEFAULT 'active',  -- active/past_due/cancelled

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Architecture Decisions

### 1. Organization-First Model

Every user belongs to exactly one organization:
- First user to sign up automatically creates an organization
- They become the "owner" with full permissions
- Owner can invite additional users (optional)
- All settings and usage are tracked at organization level

### 2. Settings Inheritance

```
Organization
  ├─ DocuWare Credentials (shared by all users in org)
  ├─ Google Drive Connection (shared by all users in org)
  └─ AI Settings (shared prompts, categories)

Users
  └─ Individual preferences (UI settings, notifications)
```

**Why?** A small business typically has ONE DocuWare instance, ONE Google Drive account. All employees should use the same connection.

### 3. Granular Usage Tracking

Log EVERY billable action with rich metadata:
- Enables flexible billing models (switch anytime)
- Provides usage analytics for customers
- Helps detect abuse or unusual patterns
- Can generate detailed invoices

### 4. Flexible Billing System

The `subscriptions` table supports multiple billing models:

**Per-Document (Current):**
```json
{
  "plan_type": "per_document",
  "price_per_document": 0.10
}
```

**Tiered (Future):**
```json
{
  "plan_type": "tiered",
  "monthly_base_fee": 99.00,
  "monthly_document_limit": 1000,
  "overage_price_per_document": 0.05
}
```

**Custom (Enterprise):**
```json
{
  "plan_type": "custom",
  "monthly_base_fee": 499.00,
  "monthly_document_limit": 10000,
  "custom_terms": "Annual contract, volume discounts apply"
}
```

---

## User Flows

### New User Signup Flow

```
1. User clicks "Sign Up" on login page
   ↓
2. Auth0 handles authentication (Google/email/etc.)
   ↓
3. Backend receives Auth0 callback
   ↓
4. Check: Does user have organization_id?
   ├─ NO → Redirect to /onboarding.html
   │        ├─ "Welcome! Let's set up your organization"
   │        ├─ Enter: Company name, billing email
   │        ├─ Choose initial plan (or start trial)
   │        ├─ Create organization in database
   │        ├─ Link user as owner
   │        └─ Redirect to /settings.html (configure connectors)
   │
   └─ YES → Redirect to /index.html (dashboard)
            └─ Show organization usage stats
```

### Existing User Login Flow

```
1. User logs in via Auth0
   ↓
2. Backend validates token
   ↓
3. Load user + organization data
   ↓
4. Redirect to /index.html
   ↓
5. Display:
   ├─ Organization name
   ├─ Usage this month (e.g., "150/1000 documents")
   ├─ Upload interface
   └─ Access to settings (based on role)
```

### Settings Access

```
User Role Permissions:

Owner:
  ✅ Configure DocuWare/Google Drive
  ✅ Manage billing and subscription
  ✅ Invite/remove users
  ✅ View all usage data
  ✅ Delete organization

Admin:
  ✅ Configure DocuWare/Google Drive
  ✅ Invite/remove members (not other admins)
  ✅ View usage data
  ❌ Manage billing
  ❌ Delete organization

Member:
  ✅ Upload and process documents
  ✅ View their own activity
  ❌ Change settings
  ❌ View billing
  ❌ Invite users
```

---

## Implementation Phases

### Phase 1: Database & Backend Foundation ⏳
**Goal:** Create the multi-tenant database schema

- [ ] Create `organizations` table
- [ ] Create `organization_settings` table
- [ ] Create `usage_logs` table
- [ ] Create `subscriptions` table
- [ ] Update `users` table (add organization_id, role)
- [ ] Update `models.py` with new Pydantic models
- [ ] Create database migration script
- [ ] Update `database.py` with new CRUD functions

**Files to modify:**
- `backend/database.py`
- `backend/models.py`
- New: `backend/migrations/001_add_organizations.sql`

---

### Phase 2: Auth Integration ⏳
**Goal:** Link users to organizations during login

- [ ] Update `get_current_user()` to include organization context
- [ ] Create `/api/organizations/create` endpoint (onboarding)
- [ ] Create `/api/organizations/current` endpoint (get org info)
- [ ] Add organization check to auth flow
- [ ] Return organization_id with user data

**Files to modify:**
- `backend/auth.py`
- `backend/routes/auth_routes.py`
- New: `backend/routes/organization_routes.py`

---

### Phase 3: Move Settings to Organization Level ⏳
**Goal:** Migrate settings from user-level to org-level

- [ ] Update connector routes to use `organization_id` instead of `user_id`
- [ ] Migrate existing settings data to organization_settings table
- [ ] Update encryption service to handle org-level configs
- [ ] Update settings frontend to show org-level settings
- [ ] Add role-based access control (only owner/admin can edit)

**Files to modify:**
- `backend/routes/connector_routes.py`
- `backend/services/encryption_service.py`
- `frontend/settings.js`

---

### Phase 4: Usage Tracking ⏳
**Goal:** Log all billable actions for future billing

- [ ] Create usage logging service
- [ ] Add usage tracking to document upload endpoints
- [ ] Add usage tracking to AI processing
- [ ] Create `/api/usage/current` endpoint (monthly stats)
- [ ] Create `/api/usage/history` endpoint (historical data)
- [ ] Create usage dashboard component for frontend

**Files to modify:**
- `backend/routes/upload.py`
- `backend/services/ai_service.py`
- New: `backend/services/usage_service.py`
- New: `backend/routes/usage_routes.py`

---

### Phase 5: Onboarding Flow ⏳
**Goal:** Smooth new user experience

- [ ] Create `onboarding.html` page
- [ ] Create organization creation form
- [ ] Add plan selection UI
- [ ] Update auth.js to detect new users
- [ ] Redirect new users to onboarding
- [ ] Add organization dashboard to index.html

**Files to create:**
- `frontend/onboarding.html`
- `frontend/onboarding.js`

**Files to modify:**
- `frontend/auth.js`
- `frontend/index.html`

---

### Phase 6: Billing Foundation (Future) 🔮
**Goal:** Prepare for Stripe integration

- [ ] Create Stripe account and API keys
- [ ] Install Stripe SDK
- [ ] Create billing portal page
- [ ] Implement webhook handlers
- [ ] Add payment method management
- [ ] Create invoice generation

---

## API Endpoints (New)

### Organizations

```
GET    /api/organizations/current          Get current user's organization
POST   /api/organizations                  Create new organization (onboarding)
PATCH  /api/organizations/current          Update organization details
GET    /api/organizations/users            List users in organization
POST   /api/organizations/invite           Invite user to organization
DELETE /api/organizations/users/:id        Remove user from organization
```

### Usage & Billing

```
GET    /api/usage/current                  Current billing period usage
GET    /api/usage/history                  Historical usage data
GET    /api/usage/logs                     Detailed usage logs (paginated)
GET    /api/billing/subscription           Current subscription details
POST   /api/billing/subscription           Update subscription plan
GET    /api/billing/invoices               Past invoices
```

---

## Environment Variables (New)

Add to `.env`:

```bash
# Billing
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Default pricing (can be overridden per organization)
DEFAULT_PRICE_PER_DOCUMENT=0.10
DEFAULT_TRIAL_DAYS=14
DEFAULT_TRIAL_DOCUMENT_LIMIT=50
```

---

## Migration Strategy

For existing users in the database:

1. **Create a default organization** for each existing user
2. **Make them the owner** of that organization
3. **Migrate their settings** to organization_settings
4. **Set up a trial subscription** for them

Script: `backend/migrations/migrate_existing_users.py`

---

## Future Enhancements

### User Invitations
- Email-based invitation system
- Pending invites table
- Accept/decline flow

### Team Management
- Role management UI
- Activity logs (audit trail)
- User permissions granularity

### Advanced Billing
- Usage alerts (80% of limit reached)
- Auto-upgrade when limit exceeded
- Annual billing discounts
- Promotional codes

### Analytics Dashboard
- Documents processed over time
- Cost trends
- Category breakdown
- Processing success rates

---

## Notes & Decisions

### Why SQLite for Multi-Tenant?

For initial launch, SQLite is fine because:
- All tenants share one database (simple)
- Usage is low-scale initially
- Easy to migrate to PostgreSQL later if needed

**Migration path:** SQLite → PostgreSQL when we hit scale limits.

### Why Organization-Level Settings?

Small businesses typically have:
- ONE DocuWare instance (not one per employee)
- ONE Google Drive workspace
- Shared document workflows

Therefore, connector settings should be shared across all users in the organization.

### Why Granular Usage Logs?

Instead of just counting documents, we log:
- File sizes (for storage billing)
- Processing time (for compute costs)
- AI tokens used (for API cost tracking)
- Success/failure rates (for quality metrics)

This gives us flexibility to:
- Change billing models without losing historical data
- Provide detailed invoices to customers
- Analyze costs and optimize pricing
- Detect and prevent abuse

---

## Success Metrics

After implementation, we should track:

1. **Onboarding completion rate**: % of signups that complete setup
2. **Time to first document**: How long until new user processes first doc
3. **Monthly active organizations**: How many orgs use the system each month
4. **Average documents per org**: Usage patterns
5. **Churn rate**: Organizations that cancel/stop using
6. **Revenue per organization**: Billing effectiveness

---

## Security Considerations

### Data Isolation
- All queries MUST filter by `organization_id`
- Users can only access their organization's data
- Add middleware to validate organization context

### Credentials Storage
- Organization settings are encrypted (already implemented)
- Only users with admin/owner role can view/edit credentials
- Audit log for credential access

### Billing Security
- Prevent usage manipulation
- Server-side usage tracking only (never trust client)
- Validate document counts before billing
- Rate limiting to prevent abuse

---

## Contact & Questions

For questions about this architecture, refer to:
- This document
- Database schema: `backend/database.py`
- API routes: `backend/routes/`
- Models: `backend/models.py`

Last updated: 2025-11-13
