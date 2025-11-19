# DocuFlow Docker - Quick Start Guide

Get DocuFlow running in 5 minutes using Docker.

## Prerequisites

- Docker & Docker Compose installed
- Domain name (for production) or localhost (for development)
- API keys: Auth0, Anthropic, Google OAuth

## Development Setup (Local Testing)

### 1. Clone and Configure

```bash
git clone https://github.com/yourusername/DocuFlow.git
cd DocuFlow

# Copy environment template
cp .env.docker .env
```

### 2. Generate Encryption Key

```bash
# Generate and add to .env
make env

# Or manually:
echo "ENCRYPTION_KEY=$(openssl rand -base64 32)" >> .env
```

### 3. Fill in Required Variables

Edit `.env` and add:

```bash
# REQUIRED: Get from https://console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-your-key-here

# REQUIRED: Get from https://manage.auth0.com
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=https://your-api-identifier

# Set database password
DB_PASSWORD=your_secure_password
```

### 4. Start Everything

```bash
# Option 1: Using Makefile (easiest)
make install

# Option 2: Manual commands
docker-compose build
docker-compose up -d
docker-compose exec backend python -c "from backend.database import init_db; init_db()"
```

### 5. Access Application

- **Frontend:** http://localhost
- **API Docs:** http://localhost/docs
- **Logs:** `make logs` or `docker-compose logs -f`

---

## Production Deployment (DigitalOcean/AWS)

### Step 1: Server Setup

```bash
# SSH into your server
ssh root@your-server-ip

# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone repository
git clone https://github.com/yourusername/DocuFlow.git
cd DocuFlow
```

### Step 2: Configure Environment

```bash
# Create production .env
cp .env.docker .env
nano .env

# Fill in all required values (Auth0, Anthropic, etc.)
# Use STRONG passwords for DB_PASSWORD
```

### Step 3: Set Up SSL (Required for Production)

```bash
# Install Certbot
apt install certbot -y

# Point your domain to server IP first (DNS A record)

# Get SSL certificate
certbot certonly --standalone -d yourdomain.com

# Certificates saved to:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

### Step 4: Deploy

```bash
# Start with production config
make prod-up

# Or manually:
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Step 5: Verify Deployment

```bash
# Check service health
make health

# View logs
make logs

# Test endpoints
curl https://yourdomain.com/health
```

### Step 6: Enable Auto-Restart

```bash
# Create systemd service
cat > /etc/systemd/system/docuflow.service << 'EOF'
[Unit]
Description=DocuFlow
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/DocuFlow
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down

[Install]
WantedBy=multi-user.target
EOF

systemctl enable docuflow
systemctl start docuflow
```

---

## Common Tasks

### View Logs

```bash
# All services
make logs

# Specific service
make logs-backend
make logs-db

# Or with docker-compose
docker-compose logs -f backend
```

### Backup Database

```bash
# Create backup
make backup

# Backups saved to ./backups/backup_YYYYMMDD_HHMMSS.sql
```

### Restore Database

```bash
make restore FILE=backups/backup_20250119_120000.sql
```

### Scale Backend (Handle More Traffic)

```bash
# Run 3 backend instances
make scale N=3

# Back to 1 instance
make scale N=1
```

### Update to Latest Version

```bash
# Pull latest code and rebuild
make update

# Or manually:
git pull origin main
docker-compose up -d --build
```

### Database Shell

```bash
# PostgreSQL shell
make shell-db

# Then run SQL:
# SELECT * FROM users;
# SELECT * FROM organizations;
```

### Backend Shell

```bash
# Python shell in container
make shell

# Or run Python commands directly:
docker-compose exec backend python -c "
from backend.database import get_user_by_email
user = get_user_by_email('test@example.com')
print(user)
"
```

---

## Architecture Explanation

### What's Running?

1. **Nginx (Frontend) - Port 80/443**
   - Serves your HTML/CSS/JS files
   - Proxies `/api/*` requests to backend
   - Handles SSL termination

2. **FastAPI Backend - Port 8000 (internal)**
   - Python application server
   - Handles authentication, document processing
   - Uses Uvicorn in dev, Gunicorn in production

3. **PostgreSQL Database - Port 5432 (internal)**
   - Stores users, organizations, documents
   - Persistent data in Docker volume

4. **Redis Cache - Port 6379 (internal)**
   - Session storage
   - Rate limiting
   - Future: Background job queue

### How They Communicate

```
User Browser
    │
    ├─── / (static files) ──────► Nginx ──► HTML/CSS/JS files
    │
    └─── /api/* ───────────────► Nginx ──► Backend:8000
                                              │
                                              ├─► PostgreSQL:5432
                                              └─► Redis:6379
```

### Data Persistence

- **Database:** Stored in Docker volume `postgres_data`
- **Redis:** Stored in Docker volume `redis_data`
- **Uploads:** Stored in `./storage/` (bind mount)
- **Backups:** Stored in `./backups/` (bind mount)

Even if containers are destroyed, your data persists in volumes.

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
make logs-backend

# Common issues:
# 1. Missing environment variables
cat .env | grep AUTH0

# 2. Port already in use
sudo lsof -i :80
sudo lsof -i :8000

# 3. Database not ready
docker-compose exec db pg_isready -U docuflow
```

### Can't Access Application

```bash
# Check services are running
docker-compose ps

# Should show all services as "Up"

# Check health
make health

# Check firewall (production)
sudo ufw status
sudo ufw allow 80
sudo ufw allow 443
```

### Database Connection Error

```bash
# Check database is running
docker-compose ps db

# Check credentials in .env
cat .env | grep DB_PASSWORD

# Test connection
docker-compose exec backend python -c "
import sqlite3
conn = sqlite3.connect('/app/storage/database/docuflow.db')
print('Connected!')
"
```

### Out of Disk Space

```bash
# Check disk usage
df -h

# Clean up Docker
docker system prune -a -f

# Clean old backups
find ./backups -name "*.sql" -mtime +30 -delete
```

### SSL Certificate Expired

```bash
# Renew certificate
certbot renew

# Restart Nginx
docker-compose restart frontend
```

---

## Costs

### Small Setup (< 100 users)

**DigitalOcean Droplet** - $24/month
- 2 vCPU, 4GB RAM, 80GB SSD
- Handles ~100 concurrent users
- All containers on single server

### Medium Setup (100-1000 users)

**DigitalOcean/AWS** - ~$100/month
- 4 vCPU, 8GB RAM
- Managed PostgreSQL (DigitalOcean Managed Database: $15/mo)
- Separate Redis instance

### Large Setup (1000+ users)

**AWS/GCP** - $500+/month
- Auto-scaling backend (ECS/Fargate)
- RDS PostgreSQL Multi-AZ
- ElastiCache Redis cluster
- CloudFront CDN

---

## Next Steps

1. **Set up monitoring:**
   - Add Sentry for error tracking
   - Add Prometheus + Grafana for metrics

2. **Enable backups:**
   - Automated daily backups (included in prod config)
   - Off-site backup storage (S3, Backblaze)

3. **Configure CI/CD:**
   - GitHub Actions for automated testing
   - Auto-deploy on push to main

4. **Scale when needed:**
   - Add load balancer
   - Multiple backend instances
   - Separate database server

---

## Support

Need help? Check:
- Full docs: `DOCKER_DEPLOYMENT.md`
- GitHub issues: https://github.com/yourusername/DocuFlow/issues
- Email: support@docuflow.com

---

## Quick Command Reference

```bash
make help          # Show all available commands
make install       # First-time setup
make up            # Start services
make down          # Stop services
make logs          # View logs
make backup        # Backup database
make health        # Check service health
make scale N=3     # Scale to 3 backend instances
make update        # Update to latest version
make clean         # Remove all containers (CAUTION)
```
