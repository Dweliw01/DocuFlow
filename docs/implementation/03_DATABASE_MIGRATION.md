# 03: Database Migration - SQLite to PostgreSQL

**Status:** 🟡 In Progress (90% Complete)
**Priority:** HIGH
**Timeline:** Week 3-4
**Dependencies:** 02_DOCKER_SETUP (PostgreSQL container)
**Branch:** `refactor/v2-architecture`

---

## Overview

Migrate DocuFlow from SQLite (development) to PostgreSQL (production) while maintaining backward compatibility for local development.

### Goals

1. **Dual Database Support** - SQLite for dev, PostgreSQL for production
2. **Alembic Migrations** - Version-controlled schema changes
3. **ORM Models** - SQLAlchemy models for all tables
4. **Zero Downtime** - Seamless transition for existing users

---

## Implementation Progress

### Completed Tasks

- [x] Install SQLAlchemy 2.0 + asyncpg + Alembic
- [x] Create SQLAlchemy ORM models (`db_models.py`)
- [x] Set up Alembic configuration (`alembic.ini`, `env.py`)
- [x] Create initial migration (full schema)
- [x] Add `DATABASE_URL` environment variable support
- [x] Create database connection abstraction (`db_connection.py`)
- [x] Update `database.py` to support both SQLite and PostgreSQL
- [x] Test migration runs successfully on SQLite
- [x] Write data migration script (`migrations/migrate_sqlite_to_postgres.py`)
- [x] Add PostgreSQL-specific indexes migration (`alembic/versions/add_postgres_indexes.py`)

### Remaining Tasks

- [ ] Test with PostgreSQL database (Docker)
- [ ] Update repository/service code to use SQLAlchemy ORM (future)
- [ ] Performance testing with PostgreSQL

---

## Architecture

### Database Configuration

```
DATABASE_URL environment variable
         │
         ├── Not set / "sqlite:///..."
         │   └── Uses SQLite (docuflow.db)
         │       └── Development mode
         │
         └── "postgresql://..."
             └── Uses PostgreSQL
                 └── Production mode
```

### File Structure

```
backend/
├── database.py           # Main database module (updated)
│   ├── DATABASE_URL      # From environment
│   ├── DB_TYPE           # "sqlite" or "postgresql"
│   ├── get_db()          # Async connection (supports both)
│   ├── get_db_connection()  # Sync connection (SQLite only)
│   └── init_database()   # Creates tables (SQLite only, skips for PostgreSQL)
│
├── db_connection.py      # Connection abstraction layer (NEW)
│   ├── DatabaseConnection    # Unified interface
│   ├── get_db_connection()   # Async, returns wrapper
│   └── get_sync_db_connection()  # Sync SQLite only
│
├── db_models.py          # SQLAlchemy ORM models (NEW)
│   ├── Organization
│   ├── User
│   ├── Batch
│   ├── ConnectorConfig
│   ├── FieldMapping
│   ├── OrganizationSetting
│   ├── UsageLog
│   ├── Subscription
│   ├── DocumentMetadata
│   └── FieldCorrection
│
└── alembic/              # Migration system (NEW)
    ├── alembic.ini
    ├── env.py
    └── versions/
        └── 54c6d18ecdb8_initial_schema.py
```

---

## SQLAlchemy Models

All 10 tables have been modeled in `db_models.py`:

| Model | Table | Description |
|-------|-------|-------------|
| `Organization` | `organizations` | Multi-tenant orgs |
| `User` | `users` | User accounts with Auth0 |
| `Batch` | `batches` | Document batch processing |
| `ConnectorConfig` | `connector_configs` | Legacy user-level connectors |
| `FieldMapping` | `field_mappings` | Field mappings for connectors |
| `OrganizationSetting` | `organization_settings` | Org-level connector settings |
| `UsageLog` | `usage_logs` | Usage tracking for billing |
| `Subscription` | `subscriptions` | Stripe billing info |
| `DocumentMetadata` | `document_metadata` | Review workflow docs |
| `FieldCorrection` | `field_corrections` | AI learning corrections |

### Model Relationships

```
Organization (1) ──┬── (*) User
                   ├── (*) Batch
                   ├── (*) OrganizationSetting
                   ├── (*) UsageLog
                   ├── (1) Subscription
                   ├── (*) DocumentMetadata
                   └── (*) FieldCorrection

User (1) ──┬── (*) Batch
           └── (*) ConnectorConfig ── (*) FieldMapping

DocumentMetadata (1) ── (*) FieldCorrection
```

---

## Alembic Migrations

### Setup

Alembic is configured to:
- Read `DATABASE_URL` from environment
- Default to SQLite if not set
- Support both SQLite and PostgreSQL dialects

### Commands

```bash
# Navigate to backend directory
cd backend

# Check current revision
alembic current

# Create new migration (auto-generate from model changes)
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one revision
alembic downgrade -1

# Rollback to beginning
alembic downgrade base
```

### Current Migrations

| Revision | Description | Date |
|----------|-------------|------|
| `54c6d18ecdb8` | Initial schema with multi-tenant support | 2025-11-25 |
| `pg_indexes_001` | PostgreSQL-specific performance indexes | 2025-11-25 |

---

## Database Connection Layer

### `db_connection.py`

Provides a unified interface for both SQLite and PostgreSQL:

```python
from db_connection import get_db_connection

# Get async connection (works for both databases)
conn = await get_db_connection()

# Execute query (handles placeholder conversion)
await conn.execute("SELECT * FROM users WHERE id = ?", user_id)

# Fetch results
rows = await conn.fetch("SELECT * FROM organizations")
row = await conn.fetchone("SELECT * FROM users WHERE email = ?", email)
value = await conn.fetchval("SELECT COUNT(*) FROM batches")

# Close connection
await conn.close()
```

### Placeholder Conversion

SQLite uses `?` placeholders, PostgreSQL uses `$1, $2, ...`

The `DatabaseConnection` wrapper automatically converts:
```sql
-- Your code writes:
SELECT * FROM users WHERE id = ? AND org_id = ?

-- For PostgreSQL, becomes:
SELECT * FROM users WHERE id = $1 AND org_id = $2
```

---

## Environment Configuration

### Development (SQLite - default)

```bash
# .env (or unset)
DATABASE_URL=sqlite:///./docuflow.db
```

### Production (PostgreSQL)

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/docuflow
```

### Docker Compose (PostgreSQL)

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: docuflow
      POSTGRES_USER: docuflow
      POSTGRES_PASSWORD: your-secure-password
    ports:
      - "5432:5432"

  backend:
    environment:
      DATABASE_URL: postgresql://docuflow:your-secure-password@db:5432/docuflow
```

---

## Migration to PostgreSQL

### Step 1: Start PostgreSQL

```bash
docker-compose up -d db
```

### Step 2: Set Environment

```bash
export DATABASE_URL="postgresql://docuflow:password@localhost:5432/docuflow"
```

### Step 3: Run Migrations

```bash
cd backend
alembic upgrade head
```

### Step 4: Migrate Data

```bash
# Migrate data from SQLite to PostgreSQL
python migrations/migrate_sqlite_to_postgres.py --postgres $DATABASE_URL

# Or with explicit paths
python migrations/migrate_sqlite_to_postgres.py \
    --sqlite ./docuflow.db \
    --postgres postgresql://docuflow:password@localhost:5432/docuflow

# Options:
#   --dry-run     Show what would be migrated without actually doing it
#   --clear       Clear PostgreSQL tables before migration
#   --verify-only Only verify row counts (no data transfer)
```

#### Data Migration Script Features

The `migrate_sqlite_to_postgres.py` script:

- **Preserves IDs** - All primary keys kept intact for relationship integrity
- **Dependency Order** - Tables migrated in correct order (parents first)
- **Sequence Reset** - PostgreSQL sequences updated to continue from max ID
- **Verification** - Automatic row count verification after migration
- **Dry Run** - Preview migration without making changes
- **Idempotent** - Can be run multiple times safely (ON CONFLICT DO NOTHING)

---

## Testing

### Verify SQLite Works

```bash
cd backend
python -c "
import database
print(f'DB_TYPE: {database.DB_TYPE}')
print(f'DB_PATH: {database.DB_PATH}')
conn = database.get_db_connection()
cursor = conn.execute('SELECT COUNT(*) FROM organizations')
print(f'Organizations: {cursor.fetchone()[0]}')
conn.close()
print('SQLite connection works!')
"
```

### Verify PostgreSQL Works

```bash
export DATABASE_URL="postgresql://docuflow:password@localhost:5432/docuflow"
cd backend
python -c "
import asyncio
import database
async def test():
    db = await database.get_db()
    # ... test queries
asyncio.run(test())
"
```

---

## Performance Considerations

### Indexes

The initial migration creates basic indexes. The `pg_indexes_001` migration adds PostgreSQL-specific optimizations:

#### Partial Indexes (Only index relevant rows)

| Index | Table | Condition | Purpose |
|-------|-------|-----------|---------|
| `idx_organizations_active` | organizations | `status = 'active'` | Fast active org lookups |
| `idx_batches_processing` | batches | `status = 'processing'` | Real-time status |
| `idx_docs_pending_review` | document_metadata | `status = 'pending_review'` | Review queue |
| `idx_docs_ready_upload` | document_metadata | `status = 'approved' AND uploaded = false` | Upload queue |
| `idx_usage_unbilled` | usage_logs | `billed = false` | Billing queries |

#### Composite Indexes (Multi-column for common queries)

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `idx_users_org_email` | users | `(organization_id, email)` | Org user lookups |
| `idx_batches_user_recent` | batches | `(user_id, created_at DESC)` | User's recent batches |
| `idx_docs_org_status_date` | document_metadata | `(org_id, status, processed_at DESC)` | Document filtering |
| `idx_usage_billing` | usage_logs | `(org_id, billing_period, action_type)` | Billing reports |
| `idx_corrections_learning` | field_corrections | `(org_id, field_name, created_at DESC)` | AI learning |

### Future Optimizations

- [ ] Configure connection pooling (PgBouncer)
- [ ] Set up read replicas for scaling
- [ ] Implement query caching with Redis
- [ ] Add table partitioning for usage_logs (by billing_period)

---

## Commits

| Commit | Description |
|--------|-------------|
| `3ca32ee` | feat: Add Alembic migrations and dual database support |
| `2f88638` | feat: Integrate database.py with db_connection for dual DB support |

---

## Next Steps

1. **Test with PostgreSQL** - Verify all queries work correctly
2. **Data Migration Script** - Migrate existing SQLite data
3. **Update Services** - Gradually move to SQLAlchemy ORM
4. **Performance Testing** - Benchmark PostgreSQL performance

---

## References

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/)
- [PostgreSQL Best Practices](https://wiki.postgresql.org/wiki/Performance_Optimization)
