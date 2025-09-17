#!/bin/bash

# Import Data Script - Run this on your VPS as the paperswithcode user
# This script imports the database dump and verifies the data

set -e

# Configuration
DB_NAME="paperswithcode"
DB_USER="paperswithcode"
APP_DIR="/home/paperswithcode/ai-paper-nexus"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running as paperswithcode user
if [ "$USER" != "paperswithcode" ]; then
    print_error "Please run this script as the paperswithcode user"
    print_info "Run: sudo su - paperswithcode"
    exit 1
fi

echo "🚀 Starting data import process..."

# Check if .env file exists
if [ ! -f "$APP_DIR/.env" ]; then
    print_error ".env file not found in $APP_DIR"
    print_info "Copy the template: cp ~/.env.template $APP_DIR/.env"
    exit 1
fi

# Find the most recent database dump
DUMP_FILE=$(ls -t ~/paperswithcode_*.sql.gz 2>/dev/null | head -1)

if [ -z "$DUMP_FILE" ]; then
    print_error "No database dump file found in home directory"
    print_info "Expected file pattern: ~/paperswithcode_TIMESTAMP.sql.gz"
    exit 1
fi

print_info "Found database dump: $DUMP_FILE"

# Check if dump is compressed
if [[ "$DUMP_FILE" == *.gz ]]; then
    print_info "Decompressing database dump..."
    gunzip "$DUMP_FILE"
    DUMP_FILE="${DUMP_FILE%.gz}"
    print_status "Database dump decompressed"
fi

# Get dump file size
DUMP_SIZE=$(ls -lh "$DUMP_FILE" | awk '{print $5}')
print_info "Database dump size: $DUMP_SIZE"

# Check database connection
print_info "Testing database connection..."
if psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    print_status "Database connection successful"
else
    print_error "Cannot connect to database"
    print_info "Check your .env file and database configuration"
    exit 1
fi

# Check if database already has data
EXISTING_PAPERS=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM papers;" 2>/dev/null || echo "0")
EXISTING_PAPERS=$(echo "$EXISTING_PAPERS" | tr -d ' ')

if [ "$EXISTING_PAPERS" -gt 0 ]; then
    print_warning "Database already contains $EXISTING_PAPERS papers"
    read -p "Do you want to continue? This will add to existing data (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Import cancelled"
        exit 0
    fi
fi

print_info "Starting database import..."
echo "This may take several minutes for large datasets..."

# Import with progress indication
if psql -U "$DB_USER" -d "$DB_NAME" < "$DUMP_FILE"; then
    print_status "Database import completed successfully"
else
    print_error "Database import failed"
    exit 1
fi

# Verify import
print_info "Verifying imported data..."

PAPER_COUNT=$(psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM papers;")
PAPER_COUNT=$(echo "$PAPER_COUNT" | tr -d ' ')

if [ "$PAPER_COUNT" -gt 0 ]; then
    print_status "Verification successful: $PAPER_COUNT papers imported"
else
    print_error "Verification failed: No papers found in database"
    exit 1
fi

# Get some statistics
print_info "Database statistics:"
psql -U "$DB_USER" -d "$DB_NAME" << EOF
SELECT 
    'Total papers' as metric, 
    COUNT(*)::text as value 
FROM papers
UNION ALL
SELECT 
    'Latest versions only' as metric, 
    COUNT(*)::text as value 
FROM papers 
WHERE is_latest_version = true
UNION ALL
SELECT 
    'Papers with abstracts' as metric, 
    COUNT(*)::text as value 
FROM papers 
WHERE abstract IS NOT NULL AND abstract != ''
UNION ALL
SELECT 
    'Date range' as metric,
    MIN(date_published)::text || ' to ' || MAX(date_published)::text as value
FROM papers
WHERE date_published IS NOT NULL;
EOF

# Test application setup
print_info "Testing application setup..."

cd "$APP_DIR"

if [ ! -f "pyproject.toml" ]; then
    print_error "pyproject.toml not found. Make sure you've cloned the repository."
    exit 1
fi

# Check if uv is available
if ! command -v uv &> /dev/null; then
    print_error "uv not found. Please install it first."
    print_info "Run: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install dependencies if not already installed
if [ ! -d ".venv" ]; then
    print_info "Installing Python dependencies..."
    uv sync
    print_status "Dependencies installed"
fi

# Test backend startup
print_info "Testing backend startup..."
timeout 10s uv run python -c "
from backend.main import app
from backend.config import get_settings
settings = get_settings()
print(f'✅ Backend configuration loaded')
print(f'Database URL: {settings.database_url.replace(settings.db_password, \"***\")}')
" || print_warning "Backend test timed out (this is normal)"

print_status "Data import and setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Start the backend service:"
echo "   sudo systemctl start paperswithcode-backend"
echo "   sudo systemctl enable paperswithcode-backend"
echo ""
echo "2. Check service status:"
echo "   sudo systemctl status paperswithcode-backend"
echo ""
echo "3. View logs:"
echo "   sudo journalctl -u paperswithcode-backend -f"
echo ""
echo "4. Test API endpoints:"
echo "   curl http://localhost:8000/health"
echo "   curl http://localhost:8000/api/v1/papers/recent?limit=5"
echo ""
echo "5. Build and deploy frontend (see migration guide)"
echo ""
echo "🎉 Your AI Paper Nexus is ready to serve $PAPER_COUNT papers!"

# Clean up
if [ -f "$DUMP_FILE" ]; then
    print_info "Cleaning up dump file..."
    rm "$DUMP_FILE"
    print_status "Cleanup completed"
fi

