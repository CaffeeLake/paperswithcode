#!/bin/bash

# Export Local Data Script for VPS Migration
# Run this on your local machine

set -e

echo "🚀 Starting local data export for VPS migration..."

# Configuration
LOCAL_DB_NAME="paperswithcode"
LOCAL_DB_USER="nielsrogge"
BACKUP_DIR="./deployment/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "📊 Checking database size..."
DB_SIZE=$(psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" -t -c "SELECT pg_size_pretty(pg_database_size('$LOCAL_DB_NAME'));")
echo "Database size: $DB_SIZE"

PAPER_COUNT=$(psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" -t -c "SELECT COUNT(*) FROM papers;")
echo "Paper count: $PAPER_COUNT"

echo "💾 Creating database dump..."
pg_dump -U "$LOCAL_DB_USER" -h localhost "$LOCAL_DB_NAME" > "$BACKUP_DIR/paperswithcode_$TIMESTAMP.sql"

echo "🗜️ Compressing database dump..."
gzip "$BACKUP_DIR/paperswithcode_$TIMESTAMP.sql"

DUMP_SIZE=$(ls -lh "$BACKUP_DIR/paperswithcode_$TIMESTAMP.sql.gz" | awk '{print $5}')
echo "Compressed dump size: $DUMP_SIZE"

echo "📁 Checking data files..."
if [ -d "./data" ]; then
    DATA_SIZE=$(du -sh ./data | cut -f1)
    echo "Data directory size: $DATA_SIZE"
    
    echo "📋 Data files:"
    ls -lh ./data/
else
    echo "⚠️ No data directory found"
fi

echo "✅ Export completed!"
echo ""
echo "📤 Next steps:"
echo "1. Transfer database dump to VPS:"
echo "   scp $BACKUP_DIR/paperswithcode_$TIMESTAMP.sql.gz paperswithcode@YOUR_VPS_IP:~/"
echo ""
echo "2. If you need data files on VPS:"
echo "   rsync -avz --progress ./data/ paperswithcode@YOUR_VPS_IP:~/ai-paper-nexus/data/"
echo ""
echo "3. Follow the VPS setup guide in migrate_to_vps.md"

# Create transfer script
cat > "$BACKUP_DIR/transfer_to_vps.sh" << EOF
#!/bin/bash
# Auto-generated transfer script
# Usage: ./transfer_to_vps.sh YOUR_VPS_IP

if [ -z "\$1" ]; then
    echo "Usage: \$0 YOUR_VPS_IP"
    exit 1
fi

VPS_IP=\$1

echo "📤 Transferring database dump to VPS..."
scp paperswithcode_$TIMESTAMP.sql.gz paperswithcode@\$VPS_IP:~/

echo "📤 Transferring data files to VPS..."
rsync -avz --progress ../../data/ paperswithcode@\$VPS_IP:~/ai-paper-nexus/data/

echo "✅ Transfer completed!"
echo "Now SSH into your VPS and run the import script."
EOF

chmod +x "$BACKUP_DIR/transfer_to_vps.sh"

echo "📝 Created transfer script: $BACKUP_DIR/transfer_to_vps.sh"
echo "   Run: cd deployment/backups && ./transfer_to_vps.sh YOUR_VPS_IP"
