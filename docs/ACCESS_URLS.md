# PapersWithCode - Access URLs

## 🌐 Frontend (React Application)

**Main URL:** **`http://167.235.148.241:8080`**

Open this URL in your browser to access the PapersWithCode website.

---

## 🔌 Backend API

**Base URL:** `http://167.235.148.241:8000`

### Useful Endpoints:

- **Health Check:** `http://167.235.148.241:8000/health`
- **Papers List:** `http://167.235.148.241:8000/api/v1/papers?page=1&page_size=20`
- **API Documentation:** `http://167.235.148.241:8000/docs`
- **API Base:** `http://167.235.148.241:8000/api/v1/`

---

## 🔒 Security Status

✅ **PostgreSQL Database:** SECURED (localhost only, not accessible from internet)
✅ **API Backend:** ACCESSIBLE (public, as intended)
✅ **Frontend:** ACCESSIBLE (public, as intended)
✅ **Firewall:** ACTIVE and configured

---

## 📝 Quick Start

From your MacBook or any device:

1. **Access the website:**
   Open `http://167.235.148.241:8080` in your browser

2. **Browse papers:**
   The frontend will automatically fetch data from the API

3. **Everything is secure:**
   - Your browser connects to the frontend on port 8080
   - The frontend fetches data from the API on port 8000
   - The API connects to PostgreSQL locally (secure!)

---

## 🛠️ For Developers

### Frontend Development
```bash
cd frontend
npm run dev
```
- Runs on port 8080
- Configured in `frontend/vite.config.ts`

### Backend API
```bash
uv run --env-file backend/keys.env backend/main.py
```
- Runs on port 8000
- Connects to PostgreSQL locally

### Security Verification
```bash
./scripts/verify_security.sh
```
- Checks PostgreSQL security
- Verifies firewall configuration
- Tests API connectivity

---

## 📚 Documentation

- **Network Architecture:** `docs/NETWORK_ARCHITECTURE.md`
- **PostgreSQL Security:** `docs/POSTGRES_SECURITY.md`
- **Project Structure:** `AGENTS.md`

---

**Last Updated:** October 1, 2025
**Status:** ✅ All systems operational and secure
