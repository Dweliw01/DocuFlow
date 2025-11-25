# 02 - Docker Development Environment Setup

**Status:** 🔴 Not Started
**Priority:** 🔴 HIGH
**Timeline:** Week 2-3
**Dependencies:** None
**Estimated Time:** 3-5 days

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Objectives](#objectives)
3. [Prerequisites](#prerequisites)
4. [Implementation Steps](#implementation-steps)
5. [Testing Checklist](#testing-checklist)
6. [Success Criteria](#success-criteria)
7. [Troubleshooting](#troubleshooting)
8. [Next Steps](#next-steps)

---

## Overview

Create a professional Docker-based development environment with:
- **PostgreSQL 15** (database - runs on your machine, FREE)
- **Redis 7** (caching - runs on your machine, FREE)
- **Backend API** (FastAPI with hot-reload)
- **Frontend** (static files with hot-reload)

**One command starts everything:** `docker-compose up`

---

## Objectives

**Primary Goal:** Professional local development environment

**What You'll Get:**
- ✅ PostgreSQL running locally (no cloud costs)
- ✅ Redis running locally (for future Celery tasks)
- ✅ Hot-reload for backend and frontend
- ✅ Consistent environment across machines
- ✅ Easy to reset/test

**Success Metrics:**
- `docker-compose up` starts all services
- All services healthy and communicating
- Hot-reload works for code changes
- Data persists across restarts

---

## Prerequisites

### Check Docker Installation

```bash
# Check Docker version
docker --version
# Need: Docker version 20.x or higher

# Check Docker Compose
docker-compose --version
# Need: Docker Compose version 2.x or higher

# Test Docker works
docker run hello-world
```

**If Docker NOT installed:**
- **Windows/Mac:** Download Docker Desktop from https://www.docker.com/products/docker-desktop
- **Linux:** `curl -fsSL https://get.docker.com | sh`

---

## Implementation Steps

### Step 1: Create docker-compose.yml

Create in project root:

**File:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  # PostgreSQL Database (runs on your machine)
  postgres:
    image: postgres:15-alpine
    container_name: docuflow-postgres
    environment:
      POSTGRES_USER: docuflow
      POSTGRES_PASSWORD: docuflow_dev_password
      POSTGRES_DB: docuflow
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/database/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U docuflow"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - docuflow-network

  # Redis Cache (runs on your machine)
  redis:
    image: redis:7-alpine
    container_name: docuflow-redis
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - docuflow-network

  # Backend API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    container_name: docuflow-backend
    environment:
      - DATABASE_URL=postgresql://docuflow:docuflow_dev_password@postgres:5432/docuflow
      - REDIS_URL=redis://redis:6379/0
      - ENVIRONMENT=development
      - PYTHONUNBUFFERED=1
    ports:
      - "8000:8000"
    volumes:
      # Mount code for hot-reload
      - ./backend:/app
      - /app/__pycache__
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - docuflow-network

  # Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    container_name: docuflow-frontend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    command: python -m http.server 3000
    networks:
      - docuflow-network
    depends_on:
      - backend

# Data persistence volumes
volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local

# Network for service communication
networks:
  docuflow-network:
    driver: bridge
```

---

### Step 2: Create PostgreSQL Init Script

**File:** `backend/database/init.sql`

```sql
-- Initial PostgreSQL setup
-- Runs automatically on first startup

-- Create UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify database ready
SELECT 'DocuFlow PostgreSQL initialized successfully!' AS status;
```

---

### Step 3: Create Backend Dockerfile

**File:** `backend/Dockerfile.dev`

```dockerfile
# Development Dockerfile for Backend
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Command specified in docker-compose.yml for flexibility
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

### Step 4: Create Frontend Dockerfile

**File:** `frontend/Dockerfile.dev`

```dockerfile
# Development Dockerfile for Frontend
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy frontend files
COPY . .

# Expose port
EXPOSE 3000

# Simple HTTP server for static files
CMD ["python", "-m", "http.server", "3000"]
```

---

### Step 5: Create Docker Environment File

**File:** `.env.docker` (project root)

```bash
# Docker Development Environment Variables

# Database (local PostgreSQL in Docker)
DATABASE_URL=postgresql://docuflow:docuflow_dev_password@postgres:5432/docuflow
DB_HOST=postgres
DB_PORT=5432
DB_USER=docuflow
DB_PASSWORD=docuflow_dev_password
DB_NAME=docuflow

# Redis (local Redis in Docker)
REDIS_URL=redis://redis:6379/0
REDIS_HOST=redis
REDIS_PORT=6379

# API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Security (dev only - change in production!)
SECRET_KEY=dev_secret_key_change_in_production

# OCR
USE_GOOGLE_VISION=false

# AI (add your key)
ANTHROPIC_API_KEY=your_api_key_here

# File Upload
MAX_FILE_SIZE=50
MAX_CONCURRENT_PROCESSING=5

# Storage
UPLOAD_DIR=/app/storage/uploads
PROCESSED_DIR=/app/storage/processed
```

---

### Step 6: Update Backend Config for Docker

**File:** `backend/config.py` - Add Docker support:

```python
import os

class Settings(BaseSettings):
    # ... existing settings ...

    # Database - use Docker PostgreSQL if available
    database_url: str = os.getenv(
        'DATABASE_URL',
        'sqlite:///./docuflow.db'  # Fallback to SQLite
    )

    # Redis
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # ... rest of settings ...
```

---

### Step 7: Create Database Directory

```bash
mkdir -p backend/database
touch backend/database/__init__.py
```

---

### Step 8: Test the Setup

#### 8.1 Build and Start Services

```bash
# From project root
docker-compose up --build
```

**Expected Output:**
```
Creating network "docuflow-network"
Creating volume "postgres_data"
Creating volume "redis_data"
Building backend...
Building frontend...
Creating docuflow-postgres ... done
Creating docuflow-redis    ... done
Creating docuflow-backend  ... done
Creating docuflow-frontend ... done

postgres_1  | PostgreSQL init process complete
redis_1     | Ready to accept connections
backend_1   | INFO: Uvicorn running on http://0.0.0.0:8000
frontend_1  | Serving HTTP on 0.0.0.0 port 3000
```

#### 8.2 Verify Services (New Terminal)

```bash
# Check all containers running
docker-compose ps

# Should show:
# NAME                  STATUS         PORTS
# docuflow-postgres     Up (healthy)   0.0.0.0:5432->5432/tcp
# docuflow-redis        Up (healthy)   0.0.0.0:6379->6379/tcp
# docuflow-backend      Up             0.0.0.0:8000->8000/tcp
# docuflow-frontend     Up             0.0.0.0:3000->3000/tcp
```

#### 8.3 Test PostgreSQL

```bash
docker exec -it docuflow-postgres psql -U docuflow -d docuflow -c "SELECT version();"
```

Should show PostgreSQL version.

#### 8.4 Test Redis

```bash
docker exec -it docuflow-redis redis-cli ping
```

Should output: `PONG`

#### 8.5 Test Backend API

```bash
curl http://localhost:8000/api/health
```

Should return JSON health check.

#### 8.6 Test Frontend

Open browser: http://localhost:3000

Should load your frontend.

#### 8.7 Test Hot-Reload

**Backend:**
1. Edit `backend/main.py`
2. Add a print statement
3. Check docker-compose logs - should see "Reloading..."

**Frontend:**
1. Edit `frontend/index.html`
2. Refresh browser
3. Changes visible immediately

#### 8.8 Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove data (fresh start)
docker-compose down -v
```

---

## Testing Checklist

### Container Health
- [ ] All 4 containers start successfully
- [ ] No errors in `docker-compose logs`
- [ ] PostgreSQL health check passes
- [ ] Redis health check passes

### Service Accessibility
- [ ] Can connect to PostgreSQL (localhost:5432)
- [ ] Can connect to Redis (localhost:6379)
- [ ] Backend API responds (localhost:8000)
- [ ] Frontend loads (localhost:3000)

### Hot-Reload
- [ ] Backend code changes trigger reload
- [ ] Frontend changes reflect in browser
- [ ] No rebuild needed for code changes

### Data Persistence
- [ ] PostgreSQL data survives restart
- [ ] Redis data survives restart
- [ ] Volumes created correctly

---

## Success Criteria

✅ **Docker Working:**
- [ ] `docker-compose up` starts all services
- [ ] All containers healthy
- [ ] Services communicate properly

✅ **Development Experience:**
- [ ] Hot-reload works
- [ ] Fast feedback loop
- [ ] Easy to debug

✅ **Service Functionality:**
- [ ] PostgreSQL accepts queries
- [ ] Redis accepts commands
- [ ] Backend API works
- [ ] Frontend loads

---

## Troubleshooting

### Port Already in Use

**Error:** `Bind for 0.0.0.0:5432 failed`

**Solution:**
```bash
# Windows
netstat -ano | findstr :5432

# Mac/Linux
lsof -i :5432

# Change port in docker-compose.yml
ports:
  - "5433:5432"  # Use different port
```

### Container Won't Start

```bash
# Check logs
docker-compose logs backend

# Run interactively
docker-compose run backend /bin/bash
```

### Hot-Reload Not Working

```bash
# Rebuild containers
docker-compose down
docker-compose up --build

# Verify volume mount
docker-compose config | grep volumes
```

### Out of Disk Space

```bash
# Clean up Docker
docker system prune -a
docker volume prune
```

---

## Next Steps

**After Docker setup complete:**

1. ✅ Mark `02_DOCKER_SETUP` as completed in tracker
2. 📝 Update README with Docker instructions
3. 🗄️ Ready for `03_DATABASE_MIGRATION` (PostgreSQL now running!)

**Git Commit:**

```bash
git add docker-compose.yml backend/Dockerfile.dev frontend/Dockerfile.dev
git commit -m "feat: Add Docker development environment

- PostgreSQL 15 container for local development
- Redis 7 container for caching
- Hot-reload enabled for backend and frontend
- Health checks and data persistence
- One command to start all services

Related: V2 Architecture Phase 1 - Docker Setup"
```

---

**🎯 Goal:** Professional dev environment running locally (FREE!)

**⏱️ Time:** 3-5 days

**💡 Tip:** All your data is LOCAL and FREE!
