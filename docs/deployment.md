# Deployment & Networking

## Overview

The application runs on a Hetzner VPS (4 GB RAM / 80 GB disk).  Services are started with `./start_services.sh`, which launches:

- FastAPI backend on port `8000`
- Vite frontend on port `8080`
- Nginx reverse proxy (systemd service) exposing the public site

All production URLs live under `https://paperswithcode.co` once DNS and HTTPS are configured.

## Network Topology

```
Internet → Nginx (80/443)
   ↳ FastAPI backend (localhost:8000)
   ↳ Frontend static assets or dev server (localhost:8080)
   ↳ PostgreSQL (localhost:5432, firewalled except for approved IPs)
```

Start and stop both app services with:

```bash
./start_services.sh
./stop_services.sh
```

Logs are written to `logs/backend.log` and `logs/frontend.log`.

## DNS Checklist

1. Point both `paperswithcode.co` and `www.paperswithcode.co` A records to the server IP (`167.235.148.241`).
2. Verify propagation:
   ```bash
   dig +short paperswithcode.co A
   ```
3. Confirm the resolver returns the server IP before requesting TLS certificates.

## HTTPS Setup

Run the helper script after DNS propagates:

```bash
cd /root/python_projects/paperswithcode
./setup_ssl.sh
```

The script:
- Validates DNS
- Requests Let’s Encrypt certificates via Certbot
- Writes `/etc/nginx/sites-available/paperswithcode.co`
- Enables HTTP→HTTPS redirects
- Registers `certbot.timer` for automatic renewal

Validate certificates:

```bash
sudo certbot certificates
sudo certbot renew --dry-run
```

## Access & Smoke Tests

- Frontend: `https://paperswithcode.co`
- API base: `https://paperswithcode.co/api/v1/`
- Health probe: `https://paperswithcode.co/health`
- Docs: `https://paperswithcode.co/docs`

Local environment (without SSL):

```bash
curl http://localhost:8000/health
open http://localhost:8080
```

## Troubleshooting

| Symptom | Actions |
| --- | --- |
| DNS still points to old IP | Re-run `dig`, wait for TTL, or use DNSChecker. |
| `setup_ssl.sh` fails ACME challenge | Ensure port 80 is open (`sudo ufw status`), Nginx is running, and DNS is correct. |
| Browser shows mixed content | Ensure frontend uses `https://paperswithcode.co/api/v1/` and not hard-coded HTTP URLs. |
| Certificate not renewing | `sudo systemctl status certbot.timer`; re-run `certbot renew --dry-run`. |
| Need to reload Nginx | `sudo nginx -t && sudo systemctl reload nginx`. |

## Useful Commands

```bash
# Service status
sudo systemctl status nginx
sudo systemctl status certbot.timer

# Follow logs
sudo tail -f /var/log/nginx/paperswithcode_error.log
sudo tail -f /var/log/nginx/paperswithcode_access.log

# Check open ports
sudo lsof -nP -iTCP -sTCP:LISTEN | grep -E '8000|8080|80|443'
```

_Last updated: 7 November 2025_
