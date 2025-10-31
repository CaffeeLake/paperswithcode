# HTTPS Setup Guide for PapersWithCode

This guide explains how to set up HTTPS for your PapersWithCode deployment using Nginx and Let's Encrypt.

## Overview

The HTTPS setup uses:
- **Nginx** as a reverse proxy server
- **Let's Encrypt** for free SSL certificates
- **Certbot** for automatic certificate management and renewal

## Architecture

```
Internet (HTTPS/443) → Nginx → Backend (localhost:8000)
                              → Frontend (localhost:8080)
```

Nginx handles:
- SSL termination (HTTPS → HTTP)
- Request routing to backend/frontend
- Security headers
- Static file caching
- WebSocket support for Vite HMR

## Prerequisites

1. **Domain Name**: You need a domain pointing to your server
   - Domain: `paperswithcode.co`
   - Server IP: `167.235.148.241`

2. **DNS Configuration**: Update your domain's A record
   - Go to your domain registrar's DNS settings
   - Add/update A record: `paperswithcode.co` → `167.235.148.241`
   - Add/update A record: `www.paperswithcode.co` → `167.235.148.241`
   - Wait 5-10 minutes for DNS propagation

3. **Firewall**: Ensure ports 80 and 443 are open
   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

## Installation

### 1. Install Nginx and Certbot

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 2. Configure Nginx

The Nginx configuration is already set up at `/etc/nginx/sites-available/paperswithcode.co`.

Key features:
- Proxies `/api/*` to FastAPI backend (port 8000)
- Proxies `/` to Vite frontend (port 8080)
- Handles `/docs`, `/redoc`, `/health` endpoints
- Redirects `www.paperswithcode.co` to `paperswithcode.co`
- WebSocket support for Vite HMR
- Security headers
- Thumbnail caching

### 3. Verify DNS Configuration

Check if your domain points to the correct IP:

```bash
dig +short paperswithcode.co A
# Should return: 167.235.148.241

curl -4 -s ifconfig.me
# Should return: 167.235.148.241
```

If the IPs don't match, update your DNS and wait for propagation.

### 4. Obtain SSL Certificate

Run the SSL setup script:

```bash
cd /root/python_projects/paperswithcode
./setup_ssl.sh
```

This script will:
1. ✅ Verify DNS configuration
2. ✅ Check Nginx status
3. ✅ Obtain SSL certificate from Let's Encrypt
4. ✅ Configure Nginx for HTTPS
5. ✅ Set up automatic certificate renewal
6. ✅ Enable HTTP → HTTPS redirect

**Manual method** (if you prefer):

```bash
sudo certbot --nginx \
    -d paperswithcode.co \
    -d www.paperswithcode.co \
    --non-interactive \
    --agree-tos \
    --email your-email@example.com \
    --redirect
```

## Verification

### Check Certificate Status

```bash
sudo certbot certificates
```

### Test HTTPS

```bash
# Test main site
curl -I https://paperswithcode.co

# Test API
curl https://paperswithcode.co/api/v1/papers/recent?limit=1

# Test API docs
curl -I https://paperswithcode.co/docs
```

### Access Your Site

- **Main Site**: https://paperswithcode.co
- **API Docs**: https://paperswithcode.co/docs
- **Health Check**: https://paperswithcode.co/health

## Certificate Renewal

Certbot automatically sets up a systemd timer for certificate renewal.

### Check Renewal Status

```bash
# Check if renewal timer is active
sudo systemctl status certbot.timer

# Test renewal (dry run)
sudo certbot renew --dry-run

# Force renewal (if needed)
sudo certbot renew --force-renewal
```

### Manual Renewal

If automatic renewal fails, you can manually renew:

```bash
sudo certbot renew
sudo systemctl reload nginx
```

Certificates are valid for 90 days and are automatically renewed when they have 30 days or less remaining.

## Nginx Management

### Common Commands

```bash
# Test configuration
sudo nginx -t

# Reload configuration (without downtime)
sudo systemctl reload nginx

# Restart Nginx
sudo systemctl restart nginx

# Check status
sudo systemctl status nginx

# View logs
sudo tail -f /var/log/nginx/paperswithcode_access.log
sudo tail -f /var/log/nginx/paperswithcode_error.log
```

### Configuration Files

- **Main config**: `/etc/nginx/sites-available/paperswithcode.co`
- **Enabled config**: `/etc/nginx/sites-enabled/paperswithcode.co` (symlink)
- **Access logs**: `/var/log/nginx/paperswithcode_access.log`
- **Error logs**: `/var/log/nginx/paperswithcode_error.log`

## Troubleshooting

### DNS Not Propagating

**Problem**: Domain doesn't point to your server yet.

**Solution**:
1. Check DNS: `dig +short paperswithcode.co A`
2. Wait 5-10 minutes for DNS propagation
3. Try from different location: https://dnschecker.org/

### Certificate Verification Failed

**Problem**: Let's Encrypt can't verify domain ownership.

**Possible causes**:
1. DNS not pointing to server
2. Port 80 not accessible from internet
3. Nginx not running
4. Firewall blocking port 80

**Solution**:
```bash
# Check if port 80 is accessible
curl -I http://paperswithcode.co

# Check firewall
sudo ufw status

# Check Nginx
sudo systemctl status nginx

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
```

### Nginx Configuration Error

**Problem**: Nginx fails to start after changes.

**Solution**:
```bash
# Test configuration
sudo nginx -t

# View detailed error
sudo journalctl -u nginx -n 50

# Restore backup if needed
sudo cp /etc/nginx/sites-available/paperswithcode.co.bak /etc/nginx/sites-available/paperswithcode.co
sudo systemctl restart nginx
```

### Backend/Frontend Not Accessible

**Problem**: HTTPS works but backend/frontend doesn't respond.

**Solution**:
```bash
# Check if services are running
ps aux | grep uvicorn
ps aux | grep vite

# Check if ports are listening
netstat -tlnp | grep 8000
netstat -tlnp | grep 8080

# Start services if needed
cd /root/python_projects/paperswithcode
./start_services.sh

# Check Nginx proxy logs
sudo tail -f /var/log/nginx/paperswithcode_error.log
```

### Certificate Expiring Soon

**Problem**: Certificate is about to expire.

**Solution**:
```bash
# Check certificate expiry
sudo certbot certificates

# Renew certificate
sudo certbot renew

# Check renewal timer
sudo systemctl status certbot.timer

# Enable timer if disabled
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

## Security Best Practices

### 1. Keep Software Updated

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Monitor Certificate Expiry

Set up monitoring to alert you if automatic renewal fails:

```bash
# Add to crontab (crontab -e)
0 0 * * * certbot renew --quiet --deploy-hook "systemctl reload nginx"
```

### 3. Review Nginx Logs Regularly

```bash
# Check for suspicious activity
sudo tail -100 /var/log/nginx/paperswithcode_access.log
```

### 4. Use Strong SSL Configuration

The current Nginx configuration includes:
- Modern SSL protocols (TLS 1.2+)
- Strong cipher suites
- Security headers (X-Frame-Options, X-Content-Type-Options, etc.)

### 5. Rate Limiting (Optional)

Add to Nginx config to prevent abuse:

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    # ... rest of config
}
```

## Updating Configuration

### Adding New Routes

Edit `/etc/nginx/sites-available/paperswithcode.co`:

```bash
sudo nano /etc/nginx/sites-available/paperswithcode.co
```

After changes:

```bash
# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Changing Backend/Frontend Ports

If you change the backend or frontend ports:

1. Update Nginx config proxy_pass directives
2. Update `start_services.sh` if needed
3. Test and reload Nginx

## Monitoring

### Check HTTPS Status

```bash
# SSL Labs test (external)
# Visit: https://www.ssllabs.com/ssltest/analyze.html?d=paperswithcode.co

# Check certificate details
openssl s_client -connect paperswithcode.co:443 -servername paperswithcode.co < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Monitor Nginx Performance

```bash
# Active connections
sudo netstat -an | grep :443 | wc -l

# Request rate
sudo tail -f /var/log/nginx/paperswithcode_access.log | pv -l -i 1 > /dev/null
```

## Backup and Restore

### Backup SSL Certificates

```bash
sudo tar -czf letsencrypt-backup-$(date +%Y%m%d).tar.gz /etc/letsencrypt
```

### Backup Nginx Configuration

```bash
sudo cp /etc/nginx/sites-available/paperswithcode.co /etc/nginx/sites-available/paperswithcode.co.bak
```

### Restore

```bash
# Restore certificates
sudo tar -xzf letsencrypt-backup-YYYYMMDD.tar.gz -C /

# Restore Nginx config
sudo cp /etc/nginx/sites-available/paperswithcode.co.bak /etc/nginx/sites-available/paperswithcode.co
sudo systemctl reload nginx
```

## Additional Resources

- **Let's Encrypt**: https://letsencrypt.org/
- **Certbot Documentation**: https://certbot.eff.org/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **SSL Labs**: https://www.ssllabs.com/ssltest/

## Quick Reference

### Essential Commands

```bash
# Setup SSL (first time)
./setup_ssl.sh

# Check certificate status
sudo certbot certificates

# Renew certificate
sudo certbot renew

# Test Nginx config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# View logs
sudo tail -f /var/log/nginx/paperswithcode_error.log

# Check services
ps aux | grep -E "uvicorn|vite"
```

### Important Files

- SSL setup script: `/root/python_projects/paperswithcode/setup_ssl.sh`
- Nginx config: `/etc/nginx/sites-available/paperswithcode.co`
- SSL certificates: `/etc/letsencrypt/live/paperswithcode.co/`
- Access logs: `/var/log/nginx/paperswithcode_access.log`
- Error logs: `/var/log/nginx/paperswithcode_error.log`

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review Nginx error logs
3. Test certificate renewal: `sudo certbot renew --dry-run`
4. Verify DNS configuration: `dig +short paperswithcode.co A`
5. Check firewall: `sudo ufw status`
