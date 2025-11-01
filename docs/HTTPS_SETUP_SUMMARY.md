# HTTPS Setup Summary

## ✅ What Has Been Completed

### 1. Software Installation
- ✅ Nginx web server installed
- ✅ Certbot (Let's Encrypt client) installed
- ✅ Python3-certbot-nginx plugin installed

### 2. Nginx Configuration
- ✅ Nginx configured as reverse proxy
- ✅ Backend API (port 8000) routing configured
- ✅ Frontend (port 8080) routing configured
- ✅ WebSocket support for Vite HMR enabled
- ✅ Security headers configured
- ✅ www → non-www redirect configured
- ✅ Configuration tested and validated

### 3. Firewall
- ✅ Port 80 (HTTP) already open
- ✅ Port 443 (HTTPS) already open

### 4. Testing
- ✅ Nginx is running successfully
- ✅ Frontend accessible via Nginx: http://167.235.148.241/
- ✅ Backend API accessible via Nginx: http://167.235.148.241/api/v1/
- ✅ Both services responding correctly

### 5. Documentation
- ✅ Complete HTTPS setup guide: `docs/HTTPS_SETUP.md`
- ✅ Quick DNS instructions: `DNS_SETUP_INSTRUCTIONS.md`
- ✅ SSL setup script: `setup_ssl.sh`
- ✅ AGENTS.md updated with deployment info

## 🔄 What You Need to Do Next

### Step 1: Update DNS (REQUIRED)

Your domain `paperswithcode.co` currently points to the wrong IP addresses.

**Current DNS**: `13.248.243.5` and `76.223.105.230` ❌
**Should point to**: `167.235.148.241` ✅

**How to update**:
1. Log in to your domain registrar (where you bought paperswithcode.co)
2. Go to DNS settings
3. Delete or update existing A records
4. Add these A records:
   - `paperswithcode.co` → `167.235.148.241`
   - `www.paperswithcode.co` → `167.235.148.241`
5. Save changes
6. Wait 5-10 minutes for DNS propagation

**Verify DNS is updated**:
```bash
dig +short paperswithcode.co A
# Should return: 167.235.148.241
```

### Step 2: Run SSL Setup Script

Once DNS is pointing to your server, run:

```bash
cd /root/python_projects/paperswithcode
./setup_ssl.sh
```

This will:
1. Verify DNS is correct
2. Obtain free SSL certificate from Let's Encrypt
3. Configure Nginx for HTTPS
4. Set up automatic certificate renewal
5. Enable HTTP → HTTPS redirect

### Step 3: Access Your Site

After SSL setup completes, your site will be available at:

- **Main Site**: https://paperswithcode.co
- **API**: https://paperswithcode.co/api/v1/
- **API Docs**: https://paperswithcode.co/docs
- **Health Check**: https://paperswithcode.co/health

All HTTP requests will automatically redirect to HTTPS.

## 📊 Current Status

| Component | Status | Details |
|-----------|--------|---------|
| Nginx | ✅ Running | Configured and tested |
| Backend | ✅ Running | Port 8000, accessible via Nginx |
| Frontend | ✅ Running | Port 8080, accessible via Nginx |
| Firewall | ✅ Configured | Ports 80 and 443 open |
| DNS | ⏳ Pending | Needs to point to 167.235.148.241 |
| SSL Certificate | ⏳ Pending | Will be obtained after DNS update |

## 🔧 Useful Commands

### Check DNS
```bash
dig +short paperswithcode.co A
```

### Check Server IP
```bash
curl -4 -s ifconfig.me
```

### Run SSL Setup
```bash
./setup_ssl.sh
```

### Manage Nginx
```bash
# Check status
sudo systemctl status nginx

# Reload configuration
sudo systemctl reload nginx

# View logs
sudo tail -f /var/log/nginx/paperswithcode_error.log
```

### Check SSL Certificate (after setup)
```bash
sudo certbot certificates
```

## 🌐 Current Access (Before DNS Update)

While waiting for DNS to propagate, you can access via IP:

- **Frontend**: http://167.235.148.241/
- **Backend API**: http://167.235.148.241/api/v1/
- **API Docs**: http://167.235.148.241/docs
- **Health Check**: http://167.235.148.241/health

## 📚 Documentation

- **Complete HTTPS Guide**: `docs/HTTPS_SETUP.md`
- **DNS Instructions**: `DNS_SETUP_INSTRUCTIONS.md`
- **Main Documentation**: `AGENTS.md` (see "HTTPS and Production Deployment" section)

## 🆘 Need Help?

If you encounter issues:

1. Check DNS: `dig +short paperswithcode.co A`
2. Check Nginx: `sudo systemctl status nginx`
3. Check logs: `sudo tail -f /var/log/nginx/paperswithcode_error.log`
4. See troubleshooting in `docs/HTTPS_SETUP.md`

## 🎯 Next Steps Summary

1. ⏳ **Update DNS** to point to `167.235.148.241`
2. ⏳ **Wait 5-10 minutes** for DNS propagation
3. ⏳ **Run** `./setup_ssl.sh` to obtain SSL certificate
4. ✅ **Enjoy** your site at https://paperswithcode.co

---

**Note**: The SSL certificate cannot be obtained until DNS is pointing to your server. This is a Let's Encrypt requirement for domain verification.
