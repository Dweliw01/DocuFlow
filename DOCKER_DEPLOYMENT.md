# DocuFlow Docker Deployment Guide

Complete guide to deploying DocuFlow using Docker containers.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Local Development Setup](#local-development-setup)
4. [Production Deployment](#production-deployment)
5. [Environment Configuration](#environment-configuration)
6. [Scaling & Load Balancing](#scaling--load-balancing)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

DocuFlow uses a **multi-container architecture**:

```
┌─────────────────────────────────────────────────────────┐
│                     Internet                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   Nginx (Frontend)    │  Port 80/443
         │   - Serves HTML/CSS/JS │
         │   - Reverse proxy      │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │   Backend API         │  Port 8000
         │   - FastAPI/Python    │
         │   - Business logic    │
         └───────┬───────┬───────┘
                 │       │
        ┌────────▼──┐  ┌─▼────────┐
        │ PostgreSQL│  │  Redis   │
        │ Database  │  │  Cache   │
        └───────────┘  └──────────┘
```

### Containers:

1. **Frontend (Nginx)**
   - Serves static HTML/CSS/JS
   - Proxies API requests to backend
   - Handles SSL termination
   - Port: 80 (HTTP), 443 (HTTPS)

2. **Backend API (FastAPI)**
   - Python application server
   - Handles authentication, document processing
   - Port: 8000 (internal)

3. **Database (PostgreSQL)**
   - User data, organizations, documents
   - Port: 5432 (internal)

4. **Cache (Redis)**
   - Session storage
   - Rate limiting
   - Port: 6379 (internal)

---

## Prerequisites

### Required Software

1. **Docker Engine** (v20.10+)
   ```bash
   # Install Docker on Ubuntu/Debian
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh

   # Start Docker
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

2. **Docker Compose** (v2.0+)
   ```bash
   # Usually included with Docker Desktop
   # Or install separately:
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

3. **Git**
   ```bash
   sudo apt-get install git
   ```

### Required Accounts

1. **Auth0** - https://auth0.com (free tier available)
2. **Anthropic API** - https://console.anthropic.com
3. **Google Cloud** - https://console.cloud.google.com (for Google Drive)
4. **Stripe** - https://stripe.com (for billing, optional initially)

---

## Local Development Setup

### Step 1: Clone and Configure

```bash
# Clone repository
git clone https://github.com/yourusername/DocuFlow.git
cd DocuFlow

# Create environment file
cp .env.docker .env

# Edit .env with your values
nano .env
```

### Step 2: Generate Encryption Key

```bash
# Generate a secure encryption key
openssl rand -base64 32

# Add to .env file:
# ENCRYPTION_KEY=<generated-key>
```

### Step 3: Build and Start Containers

```bash
# Build images
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check service health
docker-compose ps
```

### Step 4: Initialize Database

```bash
# Run migrations
docker-compose exec backend python -m backend.database

# Create test user (optional)
docker-compose exec backend python -c "
from backend.database import create_user, create_organization
user = create_user('auth0|test', 'test@example.com', 'Test User')
org = create_organization('Test Organization', user['id'])
print(f'Created user: {user}')
print(f'Created org: {org}')
"
```

### Step 5: Access Application

- Frontend: http://localhost
- API Docs: http://localhost/docs
- Backend directly: http://localhost:8000

---

## Production Deployment

### Option 1: Single Server (Recommended for < 1000 users)

**Best for:** DigitalOcean, AWS EC2, Linode, Hetzner

#### 1. Provision Server

```bash
# Recommended specs:
# - 2 vCPUs, 4GB RAM (handles ~100 concurrent users)
# - 50GB SSD
# - Ubuntu 22.04 LTS

# Example: DigitalOcean Droplet ($24/month)
# or AWS t3.medium ($30-40/month)
```

#### 2. Server Setup

```bash
# SSH into server
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Clone repository
git clone https://github.com/yourusername/DocuFlow.git
cd DocuFlow

# Create production environment file
cp .env.docker .env
nano .env  # Fill in production values

# Generate encryption key
openssl rand -base64 32  # Add to .env
```

#### 3. Configure Domain & SSL

```bash
# Point your domain to server IP
# A record: yourdomain.com -> your-server-ip

# Install Certbot for SSL
apt install certbot python3-certbot-nginx -y

# Get SSL certificate
certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Certificates will be at:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

#### 4. Deploy Application

```bash
# Build and start with production config
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Check logs
docker-compose logs -f

# Verify services are running
docker-compose ps
```

#### 5. Set Up Auto-Restart

```bash
# Create systemd service
cat > /etc/systemd/system/docuflow.service << 'EOF'
[Unit]
Description=DocuFlow Multi-Container Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/DocuFlow
ExecStart=/usr/local/bin/docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable auto-start on boot
systemctl enable docuflow
systemctl start docuflow
```

---

### Option 2: Cloud Platform (AWS ECS/Fargate)

**Best for:** Scalable production, > 1000 users

#### AWS ECS Setup

```bash
# 1. Create ECR repositories
aws ecr create-repository --repository-name docuflow-backend
aws ecr create-repository --repository-name docuflow-frontend

# 2. Build and push images
$(aws ecr get-login --no-include-email)
docker build -t docuflow-backend .
docker tag docuflow-backend:latest YOUR_ECR_URL/docuflow-backend:latest
docker push YOUR_ECR_URL/docuflow-backend:latest

# 3. Create ECS task definition (see AWS console)
# 4. Create ECS service with Application Load Balancer
# 5. Configure Auto Scaling based on CPU/Memory
```

---

### Option 3: Kubernetes (For Enterprise)

**Best for:** Multi-region, high availability, > 10,000 users

See `kubernetes/` directory for manifests (create separately).

---

## Environment Configuration

### Critical Environment Variables

```bash
# Database (REQUIRED)
DB_PASSWORD=secure_password_here

# Auth0 (REQUIRED)
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your_client_id
AUTH0_CLIENT_SECRET=your_client_secret
AUTH0_AUDIENCE=https://your-api-identifier

# Anthropic (REQUIRED)
ANTHROPIC_API_KEY=sk-ant-your-key

# Encryption (REQUIRED)
ENCRYPTION_KEY=$(openssl rand -base64 32)

# Optional but recommended
STRIPE_SECRET_KEY=sk_live_your_stripe_key
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
REDIS_URL=redis://redis:6379/0
```

### Security Best Practices

1. **Never commit .env files to git**
2. **Use strong passwords** (20+ characters)
3. **Rotate keys quarterly**
4. **Use separate Auth0 tenants** for dev/prod
5. **Enable Auth0 MFA** for admin accounts

---

## Scaling & Load Balancing

### Horizontal Scaling (Multiple Backend Instances)

```yaml
# docker-compose.scale.yml
services:
  backend:
    deploy:
      replicas: 3  # Run 3 backend instances
```

```bash
# Scale up
docker-compose -f docker-compose.yml -f docker-compose.scale.yml up -d --scale backend=3

# Nginx automatically load-balances between instances
```

### Vertical Scaling (Increase Resources)

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# Check all services
curl http://localhost/health

# Check specific service
docker-compose exec backend curl http://localhost:8000/health
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Database Backups

```bash
# Manual backup
docker-compose exec db pg_dump -U docuflow docuflow > backup_$(date +%Y%m%d).sql

# Restore from backup
docker-compose exec -T db psql -U docuflow docuflow < backup_20250119.sql

# Automated backups (already configured in docker-compose.prod.yml)
# Backups stored in ./backups/ directory
# Retention: 7 days
```

### Updates & Deployments

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Zero-downtime deployment (with load balancer)
docker-compose up -d --no-deps --scale backend=3 backend
docker-compose up -d --no-deps --scale backend=1 backend
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs backend

# Common issues:
# 1. Environment variables missing
docker-compose exec backend env | grep AUTH0

# 2. Database not ready
docker-compose exec db pg_isready -U docuflow

# 3. Port conflicts
sudo netstat -tulpn | grep 8000
```

### Database Connection Issues

```bash
# Test database connection
docker-compose exec backend python -c "
import asyncpg
import asyncio
async def test():
    conn = await asyncpg.connect(
        host='db',
        database='docuflow',
        user='docuflow',
        password='your_password'
    )
    print('Connected successfully!')
asyncio.run(test())
"
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Limit resources in docker-compose.yml:
services:
  backend:
    mem_limit: 2g
    memswap_limit: 2g
```

### SSL Certificate Issues

```bash
# Renew Let's Encrypt certificate
certbot renew

# Restart Nginx to load new certificate
docker-compose restart frontend
```

---

## Cost Estimates

### Small Deployment (< 100 users)

- **Server:** DigitalOcean Droplet (2 vCPU, 4GB RAM) - $24/mo
- **Domain:** Namecheap - $12/year
- **Auth0:** Free tier (up to 7,000 users)
- **Anthropic API:** ~$50/mo (5,000 docs/month)
- **Total:** ~$75/month

### Medium Deployment (100-1000 users)

- **Server:** AWS t3.large (2 vCPU, 8GB RAM) - $60/mo
- **RDS PostgreSQL:** db.t3.medium - $50/mo
- **Auth0:** Essentials plan - $23/mo
- **Anthropic API:** ~$500/mo (50,000 docs/month)
- **Total:** ~$633/month

### Large Deployment (1000+ users)

- **ECS Fargate:** 4 tasks - $200/mo
- **RDS PostgreSQL:** db.r5.large - $200/mo
- **ElastiCache Redis:** cache.t3.medium - $50/mo
- **Auth0:** Professional plan - $240/mo
- **Anthropic API:** ~$2,000/mo (200,000 docs/month)
- **Total:** ~$2,690/month

---

## Quick Commands Reference

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart a service
docker-compose restart backend

# View logs
docker-compose logs -f backend

# Execute command in container
docker-compose exec backend python backend/database.py

# Scale service
docker-compose up -d --scale backend=3

# Rebuild and restart
docker-compose up -d --build

# Remove all containers and volumes (CAUTION: deletes data)
docker-compose down -v

# Backup database
docker-compose exec db pg_dump -U docuflow docuflow > backup.sql

# Monitor resources
docker stats
```

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/yourusername/DocuFlow/issues
- Documentation: https://docs.docuflow.com
- Email: support@docuflow.com
