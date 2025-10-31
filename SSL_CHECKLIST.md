# SSL/HTTPS Setup Checklist

## Pre-Setup Verification ✅

- [x] Nginx installed
- [x] Certbot installed
- [x] Nginx configuration created
- [x] Firewall ports 80 and 443 open
- [x] Backend running (port 8000)
- [x] Frontend running (port 8080)
- [x] Nginx proxying correctly
- [x] Services accessible via IP (http://167.235.148.241/)

## DNS Configuration (YOUR ACTION REQUIRED)

- [ ] Log in to domain registrar (where you bought paperswithcode.co)
- [ ] Go to DNS management/settings
- [ ] Delete or update existing A records:
  - Remove: `paperswithcode.co` → `13.248.243.5`
  - Remove: `paperswithcode.co` → `76.223.105.230`
- [ ] Add new A records:
  - Add: `paperswithcode.co` → `167.235.148.241`
  - Add: `www.paperswithcode.co` → `167.235.148.241`
- [ ] Save DNS changes
- [ ] Wait 5-10 minutes for DNS propagation

### Verify DNS Update

Run this command to check if DNS is updated:

```bash
dig +short paperswithcode.co A
```

**Expected result**: `167.235.148.241`

If you see `13.248.243.5` or `76.223.105.230`, DNS hasn't propagated yet. Wait a few more minutes.

You can also check from multiple locations: https://dnschecker.org/

## SSL Certificate Setup (AFTER DNS UPDATE)

Once DNS is pointing to your server:

- [ ] Run SSL setup script:
  ```bash
  cd /root/python_projects/paperswithcode
  ./setup_ssl.sh
  ```

The script will:
- [ ] Verify DNS configuration
- [ ] Request SSL certificate from Let's Encrypt
- [ ] Configure Nginx for HTTPS
- [ ] Set up automatic certificate renewal
- [ ] Enable HTTP → HTTPS redirect

## Post-Setup Verification

After SSL setup completes:

- [ ] Visit https://paperswithcode.co (should load with HTTPS)
- [ ] Visit http://paperswithcode.co (should redirect to HTTPS)
- [ ] Test API: https://paperswithcode.co/api/v1/papers/recent?limit=1
- [ ] Test API docs: https://paperswithcode.co/docs
- [ ] Check certificate status:
  ```bash
  sudo certbot certificates
  ```

## Ongoing Maintenance

- [ ] Certificate auto-renewal is enabled (certbot.timer)
- [ ] Test renewal periodically:
  ```bash
  sudo certbot renew --dry-run
  ```
- [ ] Monitor Nginx logs:
  ```bash
  sudo tail -f /var/log/nginx/paperswithcode_error.log
  ```

## Troubleshooting

### If DNS doesn't update
- Check with your domain registrar's support
- Verify you're editing the correct domain
- Clear DNS cache: `sudo systemd-resolve --flush-caches`
- Wait longer (DNS can take up to 24 hours, but usually 5-10 minutes)

### If SSL setup fails
- Ensure DNS is pointing to your server
- Check Nginx is running: `sudo systemctl status nginx`
- Check firewall: `sudo ufw status`
- View detailed error in the script output
- See full troubleshooting guide: `docs/HTTPS_SETUP.md`

### If certificate doesn't renew automatically
- Check timer status: `sudo systemctl status certbot.timer`
- Enable timer: `sudo systemctl enable certbot.timer`
- Test renewal: `sudo certbot renew --dry-run`

## Quick Reference

| Task | Command |
|------|---------|
| Check DNS | `dig +short paperswithcode.co A` |
| Check server IP | `curl -4 -s ifconfig.me` |
| Run SSL setup | `./setup_ssl.sh` |
| Check certificate | `sudo certbot certificates` |
| Test renewal | `sudo certbot renew --dry-run` |
| Reload Nginx | `sudo systemctl reload nginx` |
| View Nginx logs | `sudo tail -f /var/log/nginx/paperswithcode_error.log` |

## Documentation

- **Complete HTTPS Guide**: `docs/HTTPS_SETUP.md`
- **Quick DNS Instructions**: `DNS_SETUP_INSTRUCTIONS.md`
- **Setup Summary**: `HTTPS_SETUP_SUMMARY.md`
- **Main Documentation**: `AGENTS.md`

---

**Current Status**: Ready for DNS update and SSL certificate installation.

**Next Step**: Update DNS A records to point to `167.235.148.241`
