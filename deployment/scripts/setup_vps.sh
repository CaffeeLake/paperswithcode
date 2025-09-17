#!/bin/bash

# VPS Setup Script - Run this on your VPS as root
# Supports Ubuntu 22.04 LTS

set -e

echo "🚀 Setting up VPS for AI Paper Nexus..."

# Configuration
APP_USER="paperswithcode"
APP_DIR="/home/$APP_USER/ai-paper-nexus"
DB_NAME="paperswithcode"
DB_USER="paperswithcode"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run this script as root"
    exit 1
fi

echo "🔄 Updating system packages..."
apt update && apt upgrade -y
print_status "System updated"

echo "📦 Installing essential packages..."
apt install -y \
    curl \
    wget \
    git \
    nginx \
    postgresql \
    postgresql-contrib \
    python3-pip \
    python3-venv \
    ufw \
    fail2ban \
    htop \
    unzip \
    certbot \
    python3-certbot-nginx
print_status "Essential packages installed"

echo "👤 Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$APP_USER"
    usermod -aG sudo "$APP_USER"
    print_status "User $APP_USER created"
else
    print_warning "User $APP_USER already exists"
fi

echo "🔥 Configuring firewall..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
print_status "Firewall configured"

echo "🗄️ Setting up PostgreSQL..."
systemctl start postgresql
systemctl enable postgresql

# Generate random password for database
DB_PASSWORD=$(openssl rand -base64 32)

sudo -u postgres psql << EOF
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH ENCRYPTED PASSWORD '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
ALTER USER $DB_USER CREATEDB;
\q
EOF

print_status "PostgreSQL configured"

# Configure PostgreSQL
PG_VERSION=$(sudo -u postgres psql -t -c "SELECT version();" | grep -oP '\d+\.\d+' | head -1)
PG_CONFIG_DIR="/etc/postgresql/$PG_VERSION/main"

# Backup original configs
cp "$PG_CONFIG_DIR/postgresql.conf" "$PG_CONFIG_DIR/postgresql.conf.backup"
cp "$PG_CONFIG_DIR/pg_hba.conf" "$PG_CONFIG_DIR/pg_hba.conf.backup"

# Add local connection for app user
echo "local   $DB_NAME   $DB_USER   md5" >> "$PG_CONFIG_DIR/pg_hba.conf"

systemctl restart postgresql
print_status "PostgreSQL restarted with new configuration"

echo "🐍 Setting up Python environment for $APP_USER..."
sudo -u "$APP_USER" bash << EOF
cd ~
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
echo 'export PATH="\$HOME/.local/bin:\$PATH"' >> ~/.bashrc
EOF

print_status "Python environment setup completed"

echo "📁 Creating application directories..."
sudo -u "$APP_USER" mkdir -p "/home/$APP_USER/backups"
sudo -u "$APP_USER" mkdir -p "/home/$APP_USER/logs"
print_status "Application directories created"

# Create environment file template
cat > "/home/$APP_USER/.env.template" << EOF
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=$DB_NAME
PWC_DB_USER=$DB_USER
PWC_DB_PASSWORD=$DB_PASSWORD
PWC_HOST=0.0.0.0
PWC_PORT=8000
PWC_ENVIRONMENT=production
PWC_DEFAULT_PAGE_SIZE=50
PWC_MAX_PAGE_SIZE=500
PWC_LOG_LEVEL=INFO
EOF

chown "$APP_USER:$APP_USER" "/home/$APP_USER/.env.template"
print_status "Environment template created"

echo "🔧 Creating systemd service..."
cat > /etc/systemd/system/paperswithcode-backend.service << EOF
[Unit]
Description=PapersWithCode FastAPI Backend
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PATH=/home/$APP_USER/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/$APP_USER/.local/bin/uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=3
StandardOutput=append:/home/$APP_USER/logs/backend.log
StandardError=append:/home/$APP_USER/logs/backend.error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
print_status "Systemd service created"

echo "🌐 Configuring Nginx..."
cat > /etc/nginx/sites-available/paperswithcode << EOF
server {
    listen 80;
    server_name _;  # Replace with your domain
    
    client_max_body_size 10M;
    
    # Frontend
    location / {
        root $APP_DIR/frontend/dist;
        try_files \$uri \$uri/ /index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
    
    # API docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
    }
    
    location /redoc {
        proxy_pass http://127.0.0.1:8000;
    }
}
EOF

# Remove default site and enable our site
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/paperswithcode /etc/nginx/sites-enabled/

nginx -t
systemctl restart nginx
systemctl enable nginx
print_status "Nginx configured"

echo "📊 Setting up log rotation..."
cat > /etc/logrotate.d/paperswithcode << EOF
/home/$APP_USER/logs/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 $APP_USER $APP_USER
    postrotate
        systemctl reload paperswithcode-backend
    endscript
}
EOF

print_status "Log rotation configured"

echo "💾 Creating backup script..."
cat > "/home/$APP_USER/backup_database.sh" << EOF
#!/bin/bash
BACKUP_DIR="/home/$APP_USER/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
mkdir -p \$BACKUP_DIR

# Database backup
pg_dump -U $DB_USER $DB_NAME | gzip > \$BACKUP_DIR/paperswithcode_\$DATE.sql.gz

# Keep only last 7 days
find \$BACKUP_DIR -name "paperswithcode_*.sql.gz" -mtime +7 -delete

echo "Backup completed: paperswithcode_\$DATE.sql.gz"
EOF

chmod +x "/home/$APP_USER/backup_database.sh"
chown "$APP_USER:$APP_USER" "/home/$APP_USER/backup_database.sh"

# Add to crontab for app user
sudo -u "$APP_USER" bash -c '(crontab -l 2>/dev/null; echo "0 2 * * * /home/'$APP_USER'/backup_database.sh") | crontab -'
print_status "Backup script created and scheduled"

echo "🔒 Configuring fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban
print_status "Fail2ban configured"

print_status "VPS setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Clone your repository as $APP_USER:"
echo "   sudo su - $APP_USER"
echo "   git clone https://github.com/your-username/ai-paper-nexus.git"
echo ""
echo "2. Copy the environment template:"
echo "   cp ~/.env.template ~/ai-paper-nexus/.env"
echo ""
echo "3. Install Python dependencies:"
echo "   cd ~/ai-paper-nexus"
echo "   uv sync"
echo ""
echo "4. Import your database dump:"
echo "   gunzip ~/paperswithcode_TIMESTAMP.sql.gz"
echo "   psql -U $DB_USER -d $DB_NAME < ~/paperswithcode_TIMESTAMP.sql"
echo ""
echo "5. Start the backend service:"
echo "   sudo systemctl enable paperswithcode-backend"
echo "   sudo systemctl start paperswithcode-backend"
echo ""
echo "6. Build and deploy frontend (see migration guide)"
echo ""
echo "🔑 Database credentials:"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
echo "   Password: $DB_PASSWORD"
echo ""
echo "💡 Save these credentials securely!"

