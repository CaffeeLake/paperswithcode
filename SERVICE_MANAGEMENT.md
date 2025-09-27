# PapersWithCode Service Management

This document describes how to manage the PapersWithCode application services (backend and frontend) using the provided shell scripts.

## 🚀 Quick Start

### Start All Services
```bash
./start_services.sh
```

### Check Service Status
```bash
./check_services.sh
```

### Stop All Services
```bash
./stop_services.sh
```

## 📋 Available Scripts

### 🟢 `start_services.sh`
**Purpose**: Starts both backend (FastAPI) and frontend (Vite) services

**Features**:
- ✅ Kills any existing processes on ports 8000 and 8080
- ✅ Starts backend with proper environment variables from `backend/keys.env`
- ✅ Starts frontend with Vite development server
- ✅ Performs health checks to ensure services are running
- ✅ Provides comprehensive logging to `logs/` directory
- ✅ Monitors services and restarts if they crash
- ✅ Graceful shutdown on Ctrl+C

**Usage**:
```bash
# Start all services (runs in foreground with monitoring)
./start_services.sh

# Start services in background (detached)
nohup ./start_services.sh > /dev/null 2>&1 &
```

**Ports**:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:8080`

### 🔴 `stop_services.sh`
**Purpose**: Gracefully stops all running services

**Features**:
- ✅ Graceful shutdown with SIGTERM first, then SIGKILL if needed
- ✅ Stops processes by port and by process name pattern
- ✅ Comprehensive cleanup of all related processes
- ✅ Status verification after shutdown

**Usage**:
```bash
./stop_services.sh
```

### 📊 `check_services.sh`
**Purpose**: Quick status check for all services

**Features**:
- ✅ Port availability check
- ✅ Process ID identification
- ✅ Health check for backend API
- ✅ Connectivity check for frontend
- ✅ Log file size reporting
- ✅ Overall system status summary

**Usage**:
```bash
./check_services.sh
```

## 🔧 Service Details

### Backend (FastAPI)
- **Port**: 8000
- **Environment**: Loaded from `backend/keys.env`
- **Command**: `uv run --env-file backend/keys.env backend/run_server.py`
- **Health Check**: `http://localhost:8000/health`
- **API Documentation**: `http://localhost:8000/docs`
- **Log File**: `logs/backend.log`

### Frontend (Vite)
- **Port**: 8080
- **Command**: `npm run dev` (in `frontend/` directory)
- **URL**: `http://localhost:8080`
- **Log File**: `logs/frontend.log`

## 📁 Log Files

All service logs are stored in the `logs/` directory:

```bash
# Monitor backend logs in real-time
tail -f logs/backend.log

# Monitor frontend logs in real-time
tail -f logs/frontend.log

# View recent backend errors
grep -i error logs/backend.log | tail -20

# Check backend startup logs
head -50 logs/backend.log
```

## 🛠️ Troubleshooting

### Services Won't Start

1. **Check port conflicts**:
   ```bash
   lsof -i :8000  # Backend port
   lsof -i :8080  # Frontend port
   ```

2. **Check environment file**:
   ```bash
   ls -la backend/keys.env
   cat backend/keys.env  # Verify database credentials
   ```

3. **Check dependencies**:
   ```bash
   # Backend dependencies
   uv sync

   # Frontend dependencies
   cd frontend && npm install
   ```

### Services Keep Crashing

1. **Check logs for errors**:
   ```bash
   tail -50 logs/backend.log
   tail -50 logs/frontend.log
   ```

2. **Check database connectivity**:
   ```bash
   # Test database connection
   uv run --env-file backend/keys.env -c "
   from backend.config import get_settings
   import psycopg2
   settings = get_settings()
   conn = psycopg2.connect(
       host=settings.db_host,
       port=settings.db_port,
       database=settings.db_name,
       user=settings.db_user,
       password=settings.db_password
   )
   print('Database connection successful!')
   conn.close()
   "
   ```

### Port Already in Use

If you get "port already in use" errors:

```bash
# Kill processes on specific ports
sudo fuser -k 8000/tcp  # Backend
sudo fuser -k 8080/tcp  # Frontend

# Or use the stop script
./stop_services.sh
```

## 🔄 Development Workflow

### Typical Development Session

1. **Start services**:
   ```bash
   ./start_services.sh
   ```

2. **Check everything is running**:
   ```bash
   ./check_services.sh
   ```

3. **Access the application**:
   - Frontend: http://localhost:8080
   - Backend API: http://localhost:8000/docs

4. **Monitor logs during development**:
   ```bash
   # In separate terminals
   tail -f logs/backend.log
   tail -f logs/frontend.log
   ```

5. **Stop services when done**:
   ```bash
   ./stop_services.sh
   ```

### Hot Reloading

Both services support hot reloading:
- **Backend**: Automatically reloads on Python file changes
- **Frontend**: Automatically reloads on TypeScript/React file changes

## 🚨 Emergency Procedures

### Force Kill All Services
```bash
# Nuclear option - kills all related processes
pkill -f "uvicorn.*backend.main:app"
pkill -f "vite"
pkill -f "npm run dev"
sudo fuser -k 8000/tcp 8080/tcp
```

### Reset Everything
```bash
# Stop services
./stop_services.sh

# Clear logs
rm -f logs/backend.log logs/frontend.log

# Restart services
./start_services.sh
```

## 📈 Performance Monitoring

### Check Resource Usage
```bash
# Check CPU and memory usage
ps aux | grep -E "(uvicorn|vite|node)" | grep -v grep

# Check port listeners
netstat -tlnp | grep -E "(8000|8080)"

# Monitor log file sizes
ls -lh logs/
```

### Health Checks
```bash
# Backend health
curl -s http://localhost:8000/health | jq

# Frontend accessibility
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080

# Database connectivity (via backend)
curl -s http://localhost:8000/api/v1/papers/stats
```

## 🔐 Security Notes

- Environment variables are loaded from `backend/keys.env`
- Database credentials are stored in the environment file
- Services run on localhost only (not exposed externally)
- No authentication required for development environment

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review log files for error messages
3. Ensure all dependencies are installed
4. Verify database is running and accessible
5. Check that ports 8000 and 8080 are available
