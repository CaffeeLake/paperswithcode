# VPS Migration Guide

Complete guide to migrate your AI Paper Nexus from local development to a VPS (Hetzner/DigitalOcean).

## Prerequisites

- VPS with Ubuntu 22.04 LTS
- At least 4GB RAM, 80GB storage (recommended: Hetzner CPX21)
- SSH access to your VPS
- Domain name (optional but recommended)

## Phase 1: VPS Setup

### 1. Initial Server Setup

```bash
# Connect to your VPS
ssh root@your-vps-ip

# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl wget git nginx postgresql postgresql-contrib python3-pip python3-venv ufw fail2ban

# Create application user
adduser --disabled-password --gecos "" paperswithcode
usermod -aG sudo paperswithcode

# Setup firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

### 2. PostgreSQL Setup

```bash
# Switch to postgres user
sudo -u postgres psql

-- Create database and user
CREATE DATABASE paperswithcode;
CREATE USER paperswithcode WITH ENCRYPTED PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE paperswithcode TO paperswithcode;
ALTER USER paperswithcode CREATEDB;
\q

# Configure PostgreSQL for remote connections (if needed)
sudo nano /etc/postgresql/14/main/postgresql.conf
# Uncomment and set: listen_addresses = 'localhost'

sudo nano /etc/postgresql/14/main/pg_hba.conf
# Add: local   paperswithcode   paperswithcode   md5

sudo systemctl restart postgresql
```

### 3. Install Python Dependencies

```bash
# Switch to application user
sudo su - paperswithcode

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Clone your repository
git clone https://github.com/your-username/ai-paper-nexus.git
cd ai-paper-nexus

# Install dependencies
uv sync
```

## Phase 2: Data Migration

### 1. Export Local Database

On your local machine:

```bash
# Create database dump
pg_dump -U nielsrogge -h localhost paperswithcode > paperswithcode_backup.sql

# Compress for faster transfer
gzip paperswithcode_backup.sql

# Check size
ls -lh paperswithcode_backup.sql.gz
```

### 2. Transfer Data to VPS

```bash
# Transfer database dump
scp paperswithcode_backup.sql.gz paperswithcode@your-vps-ip:~/

# Transfer data files (if needed for re-import)
scp -r data/ paperswithcode@your-vps-ip:~/ai-paper-nexus/

# Or use rsync for better performance
rsync -avz --progress data/ paperswithcode@your-vps-ip:~/ai-paper-nexus/data/
```

### 3. Import Database on VPS

On your VPS:

```bash
# Switch to application user
sudo su - paperswithcode

# Decompress and import
gunzip paperswithcode_backup.sql.gz
psql -U paperswithcode -d paperswithcode < paperswithcode_backup.sql

# Verify import
psql -U paperswithcode -d paperswithcode -c "SELECT COUNT(*) FROM papers;"
```

## Phase 3: Application Deployment

### 1. Environment Configuration

```bash
# Create environment file
cd ~/ai-paper-nexus
nano .env
```

Add to `.env`:
```env
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode
PWC_DB_USER=paperswithcode
PWC_DB_PASSWORD=your-secure-password
PWC_HOST=0.0.0.0
PWC_PORT=8000
PWC_ENVIRONMENT=production
PWC_DEFAULT_PAGE_SIZE=50
PWC_MAX_PAGE_SIZE=500
```

### 2. Test Application

```bash
# Test backend
cd ~/ai-paper-nexus
uv run python backend/run_server.py

# In another terminal, test API
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/papers/recent?limit=5
```

### 3. Setup Systemd Service

Create service file:

```bash
sudo nano /etc/systemd/system/paperswithcode-backend.service
```

Add:
```ini
[Unit]
Description=PapersWithCode FastAPI Backend
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=paperswithcode
Group=paperswithcode
WorkingDirectory=/home/paperswithcode/ai-paper-nexus
Environment=PATH=/home/paperswithcode/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/paperswithcode/.local/bin/uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable paperswithcode-backend
sudo systemctl start paperswithcode-backend
sudo systemctl status paperswithcode-backend
```

## Phase 4: Frontend Deployment

### 1. Build Frontend

On your local machine:
```bash
cd frontend/
npm run build
```

### 2. Transfer Frontend

```bash
# Transfer built frontend
scp -r frontend/dist/ paperswithcode@your-vps-ip:~/ai-paper-nexus/frontend/

# Or build on VPS
ssh paperswithcode@your-vps-ip
cd ~/ai-paper-nexus/frontend
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install
npm run build
```

### 3. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/paperswithcode
```

Add:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;  # Replace with your domain
    
    # Frontend
    location / {
        root /home/paperswithcode/ai-paper-nexus/frontend/dist;
        try_files $uri $uri/ /index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/paperswithcode /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Phase 5: SSL and Domain Setup

### 1. Install Certbot

```bash
sudo apt install certbot python3-certbot-nginx
```

### 2. Get SSL Certificate

```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## Phase 6: Monitoring and Maintenance

### 1. Setup Log Rotation

```bash
sudo nano /etc/logrotate.d/paperswithcode
```

Add:
```
/home/paperswithcode/ai-paper-nexus/logs/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 paperswithcode paperswithcode
}
```

### 2. Setup Backup Script

```bash
nano ~/backup_database.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/home/paperswithcode/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Database backup
pg_dump -U paperswithcode paperswithcode | gzip > $BACKUP_DIR/paperswithcode_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "paperswithcode_*.sql.gz" -mtime +7 -delete

echo "Backup completed: paperswithcode_$DATE.sql.gz"
```

Make executable and add to cron:
```bash
chmod +x ~/backup_database.sh
crontab -e
# Add: 0 2 * * * /home/paperswithcode/backup_database.sh
```

## Cost Breakdown

**Hetzner CPX21**: €8.21/month (~$9)
- 3 vCPU, 8GB RAM, 80GB SSD
- Handles 513K papers + embeddings easily
- Room for growth

**Optional additions**:
- Domain: ~$12/year
- Backup storage: ~$2/month
- Monitoring: Free (self-hosted)

**Total**: ~$11/month

## Performance Optimizations

1. **PostgreSQL tuning** for your data size
2. **Nginx caching** for static assets
3. **Connection pooling** for database
4. **Redis caching** (if needed later)

## Next Steps After Migration

1. Test all API endpoints
2. Verify data integrity
3. Setup monitoring (htop, logs)
4. Plan embedding integration
5. Setup automated deployments

