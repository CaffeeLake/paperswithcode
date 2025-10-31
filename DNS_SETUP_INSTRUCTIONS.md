# DNS Setup Instructions for paperswithcode.co

## Current Status

- **Your Server IP**: `167.235.148.241`
- **Your Domain**: `paperswithcode.co`
- **Current DNS**: Points to `13.248.243.5` and `76.223.105.230` (INCORRECT)

## What You Need to Do

### Step 1: Update DNS A Records

Go to your domain registrar (where you bought `paperswithcode.co`) and update the DNS settings:

1. **Delete or update existing A records**:
   - Remove: `paperswithcode.co` → `13.248.243.5`
   - Remove: `paperswithcode.co` → `76.223.105.230`

2. **Add new A records**:
   - `paperswithcode.co` → `167.235.148.241`
   - `www.paperswithcode.co` → `167.235.148.241`

### Step 2: Wait for DNS Propagation

DNS changes can take 5-60 minutes to propagate worldwide. Usually it's 5-10 minutes.

**Check DNS propagation**:
```bash
# From your server
dig +short paperswithcode.co A

# Should return: 167.235.148.241
```

Or use online tools:
- https://dnschecker.org/
- https://www.whatsmydns.net/

### Step 3: Run SSL Setup Script

Once DNS is pointing to your server, run:

```bash
cd /root/python_projects/paperswithcode
./setup_ssl.sh
```

This will:
1. ✅ Verify DNS is correct
2. ✅ Obtain free SSL certificate from Let's Encrypt
3. ✅ Configure Nginx for HTTPS
4. ✅ Set up automatic certificate renewal
5. ✅ Enable HTTP → HTTPS redirect

## What's Already Done

✅ Nginx installed and configured
✅ Firewall ports 80 and 443 opened
✅ Nginx reverse proxy configured for your backend and frontend
✅ SSL setup script created
✅ Automatic certificate renewal configured

## After DNS is Updated

Your site will be available at:
- **Main Site**: https://paperswithcode.co
- **API**: https://paperswithcode.co/api/v1/
- **API Docs**: https://paperswithcode.co/docs
- **Health Check**: https://paperswithcode.co/health

All HTTP requests will automatically redirect to HTTPS.

## Current Access

While waiting for DNS:
- **HTTP**: http://167.235.148.241:8080/ (direct to frontend)
- **Backend**: http://167.235.148.241:8000/ (direct to backend)
- **Via Nginx**: http://167.235.148.241/ (once DNS updates)

## Need Help?

If you encounter issues, see the full guide:
- `/root/python_projects/paperswithcode/docs/HTTPS_SETUP.md`

## Quick Commands

```bash
# Check DNS
dig +short paperswithcode.co A

# Check server IP
curl -4 -s ifconfig.me

# Run SSL setup (after DNS is updated)
./setup_ssl.sh

# Check Nginx status
sudo systemctl status nginx

# View Nginx logs
sudo tail -f /var/log/nginx/paperswithcode_error.log
```
