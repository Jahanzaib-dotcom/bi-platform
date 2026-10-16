# Production Deployment Guide

## Overview

The recommended deployment method is Docker Compose. A single `docker compose up` command starts all seven services: PostgreSQL, Redis, the FastAPI backend, one Celery worker, Celery Beat (scheduled tasks), the Next.js frontend, and Nginx as the reverse proxy and TLS terminator.

---

## Docker Compose (Recommended)

### Services

| Service | Image | Port | Description |
|---|---|---|---|
| `postgres` | postgres:16-alpine | Internal | Primary database |
| `redis` | redis:7-alpine | Internal | Task broker + pub/sub |
| `backend` | Built from `backend/Dockerfile` | Internal 8000 | FastAPI application |
| `celery-worker` | Same as backend | — | Async task workers (4 concurrent) |
| `celery-beat` | Same as backend | — | Periodic task scheduler |
| `frontend` | Built from `frontend/Dockerfile` | Internal 3000 | Next.js SSR application |
| `nginx` | nginx:alpine | 80, 443 | Reverse proxy + TLS termination |

### Step 1: Prepare Environment

```bash
# Copy the example file and fill in all secrets
cp config/.env.example .env
```

Required variables to set before production deployment:

```bash
# Database
POSTGRES_DB=bi_platform
POSTGRES_USER=bi_user
POSTGRES_PASSWORD=<strong-random-password>

# Redis
REDIS_PASSWORD=<strong-random-password>

# Application secrets
APP_SECRET_KEY=<64-char-random-string>
JWT_SECRET_KEY=<64-char-random-string>

# AI analysis (required for audit AI features)
ANTHROPIC_API_KEY=<your-anthropic-api-key>

# Optional: Google Maps discovery via SerpAPI
SERPAPI_KEY=<your-serpapi-key>

# Frontend URLs (update to your domain)
NEXT_PUBLIC_API_URL=https://yourdomain.com/api
NEXT_PUBLIC_WS_URL=wss://yourdomain.com/ws
```

Generate strong secrets:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 2: First Deployment

```bash
# Build all images and start in detached mode
docker compose up -d --build

# Verify all services are healthy
docker compose ps

# Check backend logs
docker compose logs backend

# Run database migrations (if not run automatically on startup)
docker compose exec backend alembic upgrade head
```

### Step 3: Verify Deployment

```bash
# Health check
curl http://localhost/api/v1/health

# Check API documentation
open http://localhost/docs
```

### Useful Docker Compose Commands

```bash
# View logs for a specific service
docker compose logs -f backend
docker compose logs -f celery-worker

# Restart a single service without rebuilding
docker compose restart backend

# Rebuild and restart a single service
docker compose up -d --build backend

# Scale Celery workers (2 instances)
docker compose up -d --scale celery-worker=2

# Stop all services
docker compose down

# Stop and remove volumes (WARNING: destroys database data)
docker compose down -v
```

---

## Environment Variables

### Application Variables

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `BI-Platform` | Application name (used in logs) |
| `APP_ENV` | `development` | Set to `production` for prod |
| `APP_PORT` | `8000` | Backend port |
| `APP_SECRET_KEY` | — | Required. App-level secret |
| `DEBUG` | `false` | Enable debug mode |

### Database Variables

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_DB` | `bi_platform` | Database name |
| `POSTGRES_USER` | `bi_user` | Database user |
| `POSTGRES_PASSWORD` | — | Required. Database password |
| `DATABASE_URL` | — | Full async URL (auto-constructed in Compose) |

### Redis Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_PASSWORD` | — | Required in production |
| `REDIS_URL` | — | Full URL (auto-constructed in Compose) |

### Auth Variables

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | — | Required. JWT signing key |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |

### AI Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `AI_MODEL` | `claude-opus-4-8` | Model to use for AI analysis |

### Celery Variables

| Variable | Default | Description |
|---|---|---|
| `CELERY_BROKER_URL` | — | Redis broker URL |
| `CELERY_RESULT_BACKEND` | — | Redis result backend URL |

### Storage Variables

| Variable | Default | Description |
|---|---|---|
| `SCREENSHOT_DIR` | `./storage/screenshots` | Screenshot file storage path |
| `EXPORT_DIR` | `./storage/exports` | Export file storage path |

---

## SSL Setup

### Option 1: Let's Encrypt (Recommended for Production)

**Step 1:** Install Certbot on the host.

```bash
# Ubuntu/Debian
sudo apt install certbot

# macOS (Homebrew)
brew install certbot
```

**Step 2:** Stop Nginx temporarily and obtain a certificate.

```bash
docker compose stop nginx

sudo certbot certonly --standalone \
  -d yourdomain.com \
  -d www.yourdomain.com \
  --email admin@yourdomain.com \
  --agree-tos \
  --non-interactive
```

**Step 3:** Copy certificates into the deployment directory.

```bash
mkdir -p deployment/ssl
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem deployment/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem deployment/ssl/
sudo chown $(whoami):$(whoami) deployment/ssl/*.pem
```

**Step 4:** Enable HTTPS redirect in `deployment/nginx/nginx.conf`.

Uncomment the redirect line in the HTTP server block:

```nginx
# In the HTTP server block (port 80), uncomment:
return 301 https://$host$request_uri;
```

**Step 5:** Start Nginx.

```bash
docker compose start nginx
```

**Step 6:** Set up automatic renewal.

```bash
# Add to crontab (renews and reloads Nginx)
echo "0 3 * * * certbot renew --quiet && docker compose exec nginx nginx -s reload" | sudo crontab -
```

### Option 2: Self-Signed Certificate (Development / Internal Use)

```bash
mkdir -p deployment/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deployment/ssl/privkey.pem \
  -out deployment/ssl/fullchain.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

---

## Scaling Considerations

### Horizontal Scaling

**Celery Workers**

Each Celery worker runs 4 concurrent tasks by default (`--concurrency=4`). Scale workers independently to handle more throughput:

```bash
# Run 3 worker instances
docker compose up -d --scale celery-worker=3
```

Each worker consumes approximately 500 MB–1 GB of RAM due to Playwright browser instances.

**Backend (API)**

The FastAPI backend is stateless. Behind a load balancer, run multiple instances:

```bash
docker compose up -d --scale backend=3
```

Update `deployment/nginx/nginx.conf` to distribute load across backend instances:

```nginx
upstream backend {
    server backend_1:8000;
    server backend_2:8000;
    server backend_3:8000;
    keepalive 32;
}
```

WebSocket connections use Redis pub/sub to broadcast events across all processes — no sticky sessions are required.

**Database Connection Pooling**

For high-traffic deployments, add PgBouncer in front of PostgreSQL:

```yaml
# Add to docker-compose.yml
pgbouncer:
  image: pgbouncer/pgbouncer:1.22
  environment:
    DATABASES_HOST: postgres
    DATABASES_PORT: 5432
    DATABASES_USER: bi_user
    DATABASES_PASSWORD: ${POSTGRES_PASSWORD}
    DATABASES_DBNAME: bi_platform
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 200
    DEFAULT_POOL_SIZE: 25
```

### Resource Recommendations

| Component | Minimum | Recommended (production) |
|---|---|---|
| PostgreSQL | 2 GB RAM, 20 GB disk | 4 GB RAM, 100 GB SSD |
| Redis | 512 MB RAM | 1 GB RAM |
| Backend (per instance) | 512 MB RAM | 1 GB RAM |
| Celery worker (per instance) | 1 GB RAM | 2 GB RAM |
| Frontend | 256 MB RAM | 512 MB RAM |
| Nginx | 64 MB RAM | 128 MB RAM |

---

## Backup Strategy

### PostgreSQL Database

**Automated daily backup script:**

```bash
#!/usr/bin/env bash
# Save as /etc/cron.daily/bi-platform-backup
BACKUP_DIR="/var/backups/bi-platform"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

docker compose exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-bi_user}" \
  "${POSTGRES_DB:-bi_platform}" \
  | gzip > "${BACKUP_FILE}"

# Retain only the last 30 days of backups
find "${BACKUP_DIR}" -name "postgres_*.sql.gz" -mtime +30 -delete

echo "Backup created: ${BACKUP_FILE}"
```

Make executable and test:

```bash
chmod +x /etc/cron.daily/bi-platform-backup
/etc/cron.daily/bi-platform-backup
```

**Restore from backup:**

```bash
gunzip -c postgres_20260101_030000.sql.gz | \
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-bi_user}" \
    "${POSTGRES_DB:-bi_platform}"
```

### Storage Files (Screenshots & Exports)

The `storage` Docker volume holds screenshots and export files. Back it up using `rsync` or S3 sync:

```bash
# Sync to S3
aws s3 sync /var/lib/docker/volumes/bi-platform_storage/_data \
  s3://your-bucket/bi-platform-storage/ \
  --delete
```

For cloud deployments, mount the storage volume on a persistent disk (AWS EBS, GCP Persistent Disk, etc.) rather than relying on Docker volumes.

### Redis

Redis holds only transient Celery job state. If Redis is lost in-flight jobs will need to be re-queued, but no persistent data is lost. The `appendonly yes` Redis configuration enables AOF persistence for faster recovery.

---

## Monitoring

The backend exposes Prometheus-compatible metrics at `/metrics` (requires `prometheus-client`). Add a Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: bi-platform
    static_configs:
      - targets: ['backend:8000']
    metrics_path: /metrics
```

Celery task metrics can be collected using Flower:

```bash
# Add to docker-compose.yml or run separately
docker run -p 5555:5555 mher/flower \
  celery --broker=redis://:${REDIS_PASSWORD}@redis:6379/1 flower
```

---

## Upgrading

```bash
# Pull latest code
git pull origin main

# Rebuild and restart with zero-downtime (single-node)
docker compose up -d --build --no-deps backend celery-worker frontend

# Apply any new database migrations
docker compose exec backend alembic upgrade head

# Verify health
docker compose ps
curl http://localhost/api/v1/health
```
