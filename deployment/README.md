# VPS Deployment for AI Paper Nexus

Complete deployment solution for migrating your AI Paper Nexus from local development to a VPS (Hetzner/DigitalOcean).

## 🚀 Quick Start

### 1. Export Local Data (Run on your Mac)

```bash
# Make scripts executable
chmod +x deployment/scripts/*.sh

# Export your local database and data
./deployment/scripts/export_local_data.sh

# Transfer to VPS (replace YOUR_VPS_IP)
cd deployment/backups
./transfer_to_vps.sh YOUR_VPS_IP
```

### 2. Setup VPS (Run on your VPS as root)

```bash
# SSH into your VPS
ssh root@YOUR_VPS_IP

# Download and run setup script
curl -sSL https://raw.githubusercontent.com/your-username/ai-paper-nexus/main/deployment/scripts/setup_vps.sh | bash
```

### 3. Deploy Application (Run on VPS as paperswithcode user)

```bash
# Switch to app user
sudo su - paperswithcode

# Clone repository
git clone https://github.com/your-username/ai-paper-nexus.git
cd ai-paper-nexus

# Copy environment file
cp ~/.env.template .env

# Install dependencies
uv sync

# Import data
./deployment/scripts/import_data_vps.sh

# Start services
sudo systemctl start paperswithcode-backend
sudo systemctl enable paperswithcode-backend
```

### 4. Deploy Frontend

```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Build frontend
cd ~/ai-paper-nexus/frontend
npm install
npm run build

# Restart nginx
sudo systemctl restart nginx
```

## 📊 VPS Recommendations

### Hetzner (Recommended - Better Value)
- **CPX21**: €8.21/month (~$9) - 3 vCPU, 8GB RAM, 80GB SSD ✅
- **CPX31**: €16.37/month (~$18) - 4 vCPU, 16GB RAM, 160GB SSD

### DigitalOcean
- **Regular**: $12/month - 1 vCPU, 2GB RAM, 50GB SSD (too small)
- **Premium**: $24/month - 2 vCPU, 4GB RAM, 80GB SSD

### Why Hetzner CPX21 is Perfect:
- ✅ Handles 513K papers (707MB database)
- ✅ Room for embeddings (vector search)
- ✅ 3 vCPUs for concurrent requests
- ✅ 8GB RAM for caching
- ✅ 80GB SSD with room to grow
- ✅ Best price/performance ratio

## 🗂️ What Gets Migrated

### Database (707MB)
- ✅ 513,886 papers with full metadata
- ✅ ArXiv IDs, titles, abstracts
- ✅ Publication dates, conferences
- ✅ Citation counts (if populated)
- ✅ All indexes and constraints

### Data Files (2.6GB - Optional)
- `papers-with-abstracts.json` (2.4GB)
- `evaluation-tables.json` (247MB)
- `links-between-papers-and-code.json` (162MB)
- `jul-28-methods.json` (30MB)

*Note: Data files are only needed if you plan to re-import or extend the database*

## 🔧 Architecture on VPS

```
Internet → Nginx (Port 80/443) → FastAPI Backend (Port 8000) → PostgreSQL
                ↓
        Static Files (React Frontend)
```

### Services Running:
- **Nginx**: Reverse proxy + static file serving
- **FastAPI**: Backend API (systemd service)
- **PostgreSQL**: Database with full-text search
- **Certbot**: SSL certificates (optional)
- **Fail2ban**: Security (SSH protection)

## 📈 Performance Expectations

### With Current Data (513K papers):
- **API Response Time**: 50-200ms
- **Search Queries**: 100-500ms
- **Concurrent Users**: 50-100
- **Memory Usage**: 2-4GB
- **Storage Growth**: ~1GB/month

### With Embeddings Added:
- **Vector Storage**: +2-5GB
- **Search Performance**: 200-800ms
- **Memory Usage**: 4-6GB
- **Recommended**: Upgrade to CPX31 (16GB RAM)

## 🔒 Security Features

- ✅ UFW firewall (SSH + HTTP/HTTPS only)
- ✅ Fail2ban (SSH brute force protection)
- ✅ PostgreSQL local connections only
- ✅ Nginx security headers
- ✅ SSL/TLS certificates (Certbot)
- ✅ Regular security updates

## 📊 Monitoring & Maintenance

### Automated:
- ✅ Daily database backups (2 AM)
- ✅ Log rotation (weekly)
- ✅ Service auto-restart on failure
- ✅ SSL certificate renewal

### Manual Monitoring:
```bash
# Check service status
sudo systemctl status paperswithcode-backend

# View logs
sudo journalctl -u paperswithcode-backend -f

# Check database size
psql -U paperswithcode -d paperswithcode -c "SELECT pg_size_pretty(pg_database_size('paperswithcode'));"

# Monitor resources
htop
```

## 💰 Cost Breakdown

### Hetzner CPX21 Setup:
- **VPS**: €8.21/month (~$9)
- **Domain** (optional): ~$1/month
- **Backup Storage** (optional): ~$2/month
- **Total**: ~$12/month

### Scaling Path:
1. **Start**: CPX21 ($9/month) - 513K papers
2. **Add Embeddings**: CPX31 ($18/month) - Vector search
3. **High Traffic**: CPX41 ($35/month) - 1M+ requests/day
4. **Enterprise**: Multiple servers + load balancer

## 🚀 Adding Embeddings Later

When you're ready to add vector search:

1. **Install pgvector extension**:
```sql
CREATE EXTENSION vector;
ALTER TABLE papers ADD COLUMN embedding vector(768);
```

2. **Generate embeddings** (batch process):
```python
# Use sentence-transformers or OpenAI
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
```

3. **Upgrade VPS** to CPX31 (16GB RAM) for better performance

## 🆘 Troubleshooting

### Common Issues:

**Service won't start**:
```bash
sudo journalctl -u paperswithcode-backend --no-pager
```

**Database connection failed**:
```bash
psql -U paperswithcode -d paperswithcode -c "SELECT 1;"
```

**Nginx errors**:
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

**Out of disk space**:
```bash
df -h
sudo du -sh /home/paperswithcode/* | sort -hr
```

## 📞 Support

- Check logs first: `sudo journalctl -u paperswithcode-backend -f`
- Database issues: Verify `.env` file and PostgreSQL status
- Performance issues: Monitor with `htop` and consider upgrading VPS
- SSL issues: Re-run `sudo certbot --nginx`

## 🎯 Next Steps After Deployment

1. **Test all endpoints**: API docs at `https://yourdomain.com/docs`
2. **Setup monitoring**: Consider adding Grafana + Prometheus
3. **Plan embeddings**: Choose embedding model and vector search strategy
4. **Backup strategy**: Test restore procedures
5. **Domain setup**: Configure your custom domain
6. **CDN**: Consider CloudFlare for global performance

Your AI Paper Nexus will be serving 513K papers to users worldwide for just $9/month! 🎉

