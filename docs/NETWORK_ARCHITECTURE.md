# Network Architecture & Security Configuration

## Overview

This document describes the network architecture, security setup, and access patterns for the PapersWithCode application.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User's Browser                           │
│                   (MacBook / Any Device)                     │
└────────┬────────────────────────────────────────────────────┘
         │
         │ HTTP (Ports 8080 for UI, 8000 for API)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│               Hetzner VPS (167.235.148.241)                  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Vite Dev Server (Port 8080)                         │  │
│  │  - Serves React frontend                             │  │
│  │  - Publicly accessible                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  FastAPI Backend (Port 8000)                         │  │
│  │  - Publicly accessible                               │  │
│  │  - Handles all API requests                          │  │
│  └────────────────┬─────────────────────────────────────┘  │
│                   │                                          │
│                   │ Local connection (127.0.0.1:5432)       │
│                   │                                          │
│  ┌────────────────▼─────────────────────────────────────┐  │
│  │  PostgreSQL (Port 5432)                              │  │
│  │  - Listens ONLY on localhost (127.0.0.1)            │  │
│  │  - NOT accessible from internet                      │  │
│  │  - Secured by firewall                               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Security Configuration

### PostgreSQL Database (Port 5432)
**Status: ✅ SECURE - NOT accessible from internet**

- **Listen Address**: `localhost` (127.0.0.1) only
- **Access Control**: Local connections only via `pg_hba.conf`
- **Firewall**: UFW denies all external connections to port 5432
- **Purpose**: Database is only accessible from the local VPS

**Configuration Files:**
- `/etc/postgresql/16/main/postgresql.conf` - `listen_addresses = 'localhost'`
- `/etc/postgresql/16/main/pg_hba.conf` - No remote IP addresses whitelisted
- UFW firewall rule: `5432/tcp DENY Anywhere`

### FastAPI Backend (Port 8000)
**Status: ✅ ACCESSIBLE - Required for public API**

- **Listen Address**: `0.0.0.0` (all interfaces)
- **Access**: Publicly accessible
- **Firewall**: UFW allows connections to port 8000
- **Purpose**: Serves as the API layer between frontend and database

**Key Points:**
- Backend connects to PostgreSQL locally (secure)
- Backend is intentionally public-facing
- All database queries go through the backend (proper architecture)

**Configuration:**
- UFW firewall rule: `8000/tcp ALLOW Anywhere`
- Backend config: See `backend/config.py`

### Firewall Rules (UFW)

```bash
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere      # SSH
80/tcp                     ALLOW       Anywhere      # HTTP
443/tcp                    ALLOW       Anywhere      # HTTPS
8000/tcp                   ALLOW       Anywhere      # API Backend
8080/tcp                   ALLOW       Anywhere      # Frontend Dev Server
5432/tcp                   DENY        Anywhere      # PostgreSQL (BLOCKED)
```

## Access URLs

### Frontend (React Application)
**URL:** `http://167.235.148.241:8080`

- Vite development server serving the React frontend
- Proxies API requests to the backend automatically
- Hot Module Replacement (HMR) for development

### Backend API
**URL:** `http://167.235.148.241:8000`

- Health check: `http://167.235.148.241:8000/health`
- Papers API: `http://167.235.148.241:8000/api/v1/papers`
- API docs: `http://167.235.148.241:8000/docs` (development mode)

## Frontend Access Pattern

The React frontend connects to the backend API:

1. **Browser** → `http://167.235.148.241:8080` → **Vite Dev Server** → Serves React app
2. **React App** → `http://167.235.148.241:8000/api/v1/papers` → **API Server**
3. **API Server** → `localhost:5432` → **PostgreSQL** (local connection)
4. **PostgreSQL** → Returns data → **API Server**
5. **API Server** → Returns JSON → **React App** → **Browser**

**Frontend Configuration:**
- `frontend/src/lib/api.ts` - API base URL: `http://167.235.148.241:8000/api/v1`
- `frontend/vite.config.ts` - Dev server on port 8080 with API proxy
- Frontend never directly connects to PostgreSQL (secure architecture)

## Verifying Security

### Check PostgreSQL is secured:
```bash
# Should show only localhost (127.0.0.1 and ::1)
sudo netstat -tlnp | grep 5432

# Should show: tcp        0      0 127.0.0.1:5432          0.0.0.0:*               LISTEN
```

### Check API is accessible:
```bash
# Should return: {"status":"healthy","service":"paperswithcode-api"}
curl http://167.235.148.241:8000/health

# Should return paper data
curl "http://167.235.148.241:8000/api/v1/papers?page=1&page_size=1"
```

### Check Firewall:
```bash
sudo ufw status
# Should show 5432/tcp DENY and 8000/tcp ALLOW
```

## Access from Your MacBook

When you access the website from your MacBook:

1. ✅ **You CAN access**: The frontend and API at `http://167.235.148.241:8000`
2. ❌ **You CANNOT access**: PostgreSQL directly at `167.235.148.241:5432` (this is correct and secure!)
3. ✅ **The API CAN access**: PostgreSQL locally (this is correct!)

This is the **correct and secure architecture** - the database is protected behind the API layer.

## Troubleshooting

### Browser Shows Connection Errors

If you see errors like `ERR_CONNECTION_REFUSED`, `ERR_CONNECTION_TIMED_OUT`, or `ERR_INTERNET_DISCONNECTED`:

1. **Check API is running:**
   ```bash
   sudo netstat -tlnp | grep 8000
   # Should show python3 listening on 0.0.0.0:8000
   ```

2. **Test API from server:**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Test API from external:**
   ```bash
   curl http://167.235.148.241:8000/health
   ```

4. **Check browser console:**
   - Open Developer Tools (F12)
   - Check if requests are reaching the API
   - Look for actual error messages

5. **Common causes:**
   - Temporary network issues (VPN, WiFi)
   - API server not running
   - Vite dev server connection issues (not API issues)

### Frontend Development Connection

If you're running the Vite dev server locally, you might see WebSocket connection errors like:
- `[vite] server connection lost. Polling for restart...`
- `[Vite] connected.`

These are **Hot Module Replacement (HMR)** WebSocket connections between your local Vite dev server and the browser - they are **NOT** related to the API connection and are safe to ignore.

## Production Deployment

For production, consider:

1. **HTTPS Setup**: Configure nginx with SSL certificates
2. **Domain Name**: Point a domain to the VPS IP
3. **Environment Variables**: Use proper secrets management
4. **Rate Limiting**: Implement API rate limiting
5. **Monitoring**: Set up logging and monitoring for API health

## Security Best Practices

✅ **Currently Implemented:**
- Database not exposed to internet
- Firewall blocking PostgreSQL port
- API layer protecting database
- No remote database access

✅ **Recommended Additional Steps:**
- Set up SSL/TLS for API (HTTPS)
- Implement API authentication/authorization
- Regular security updates
- Database backup strategy
- Monitor logs for suspicious activity

---

**Last Updated:** October 1, 2025
**Security Status:** ✅ PostgreSQL SECURED | ✅ API ACCESSIBLE | ✅ Architecture CORRECT
