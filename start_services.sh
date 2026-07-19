#!/bin/bash

# PapersWithCode Services Startup Script
# Manages both backend (FastAPI) and frontend (Vite) services
# Includes process cleanup, health checks, and proper logging
#
# Usage:
#   ./start_services.sh          - Start services and detach (recommended for production)
#   ./start_services.sh --monitor - Start services and monitor them (will stop on disconnect)

set -e  # Exit on any error

# Check for monitor mode
MONITOR_MODE=false
if [ "$1" = "--monitor" ] || [ "$1" = "-m" ]; then
    MONITOR_MODE=true
fi

# Ensure backend starts in production mode unless explicitly overridden
export PWC_ENVIRONMENT="${PWC_ENVIRONMENT:-production}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="/root/python_projects/paperswithcode"
BACKEND_PORT=8000
BACKEND_WORKERS="${PWC_BACKEND_WORKERS:-2}"
FRONTEND_PORT=8080
LOG_DIR="$PROJECT_ROOT/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo -e "${BLUE}🚀 PapersWithCode Services Manager${NC}"
echo -e "${BLUE}====================================${NC}"
echo -e "Project Root: ${CYAN}$PROJECT_ROOT${NC}"
echo -e "Backend Port: ${CYAN}$BACKEND_PORT${NC}"
echo -e "Frontend Port: ${CYAN}$FRONTEND_PORT${NC}"
if [ "$MONITOR_MODE" = true ]; then
    echo -e "Mode: ${YELLOW}Monitor (services will stop when script exits)${NC}"
else
    echo -e "Mode: ${GREEN}Detached (services will persist after disconnect)${NC}"
fi
echo ""

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

port_is_free() { ! check_port "$1"; }
pattern_is_gone() { ! pgrep -f "$1" >/dev/null 2>&1; }

# Poll a condition (passed as a command + args) up to `max_tenths` tenths of a
# second, returning the instant it succeeds. Used so backend restarts proceed
# as soon as the old process exits instead of sleeping a fixed window — the
# previous fixed `sleep 2; ...; sleep 1` waits kept :8000 down for ~5-6s on
# every restart, which is exactly when nginx logged `connection refused` bursts.
wait_until() {
    local max_tenths=$1
    shift
    local i=0
    while [ "$i" -lt "$max_tenths" ]; do
        if "$@"; then
            return 0
        fi
        sleep 0.1
        i=$((i + 1))
    done
    return 1
}

# Function to kill processes on a specific port
kill_port_processes() {
    local port=$1
    local service_name=$2

    if check_port $port; then
        echo -e "${YELLOW}⚠️  Port $port is in use by $service_name${NC}"
        local pids=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}🔄 Killing existing $service_name processes: $pids${NC}"
            kill -TERM $pids 2>/dev/null || true
            # Wait up to 5s for a graceful exit, proceeding the moment the port
            # frees so we minimize the restart downtime window.
            if ! wait_until 50 port_is_free "$port"; then
                kill -KILL $pids 2>/dev/null || true
                wait_until 20 port_is_free "$port" || true
            fi
        fi
    fi
}

# Function to kill processes by name pattern
kill_processes_by_pattern() {
    local pattern=$1
    local service_name=$2

    local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}🔄 Killing existing $service_name processes: $pids${NC}"
        kill -TERM $pids 2>/dev/null || true
        if ! wait_until 50 pattern_is_gone "$pattern"; then
            # Force kill any stragglers, then give them a moment to die.
            pgrep -f "$pattern" 2>/dev/null | xargs -r kill -KILL 2>/dev/null || true
            wait_until 20 pattern_is_gone "$pattern" || true
        fi
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local port=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}⏳ Waiting for $service_name to start on port $port...${NC}"

    while [ $attempt -le $max_attempts ]; do
        if check_port $port; then
            echo -e "${GREEN}✅ $service_name is ready on port $port${NC}"
            return 0
        fi

        echo -e "${YELLOW}   Attempt $attempt/$max_attempts - waiting...${NC}"
        sleep 2
        ((attempt++))
    done

    echo -e "${RED}❌ $service_name failed to start on port $port after $max_attempts attempts${NC}"
    return 1
}

# Function to check service health
check_service_health() {
    local port=$1
    local service_name=$2
    local health_endpoint=$3

    if curl -s -f "$health_endpoint" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name health check passed${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  $service_name health check failed${NC}"
        return 1
    fi
}

# Cleanup function (only used in monitor mode)
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down services...${NC}"
    kill_port_processes $BACKEND_PORT "Backend"
    kill_port_processes $FRONTEND_PORT "Frontend"
    kill_processes_by_pattern "uvicorn.*backend.main:app" "Backend"
    kill_processes_by_pattern "vite( |$)" "Frontend (vite)"
    kill_processes_by_pattern "vite preview" "Frontend (preview)"
    echo -e "${GREEN}✅ Cleanup completed${NC}"
}

# Only set up signal handlers in monitor mode
if [ "$MONITOR_MODE" = true ]; then
    trap cleanup EXIT INT TERM
fi

echo -e "${PURPLE}🧹 Cleaning up existing processes...${NC}"

# Kill existing processes
kill_port_processes $BACKEND_PORT "Backend"
kill_port_processes $FRONTEND_PORT "Frontend"
kill_processes_by_pattern "uvicorn.*backend.main:app" "Backend"
kill_processes_by_pattern "vite( |$)" "Frontend (vite)"
kill_processes_by_pattern "vite preview" "Frontend (preview)"

echo -e "${GREEN}✅ Cleanup completed${NC}"
echo ""

# Change to project directory
cd "$PROJECT_ROOT"

# Start Backend
echo -e "${PURPLE}🔧 Starting Backend (FastAPI)...${NC}"
echo -e "   Environment: ${CYAN}backend/keys.env${NC}"
echo -e "   Port: ${CYAN}$BACKEND_PORT${NC}"
echo -e "   Workers: ${CYAN}$BACKEND_WORKERS${NC}"
echo -e "   Log: ${CYAN}$BACKEND_LOG${NC}"

# Start backend in background with logging. Launch uvicorn directly from the
# project venv after loading keys.env; this avoids an extra uv/run_server parent
# process that can exit while leaving nginx pointed at a dead :8000.
set -a
source backend/keys.env
set +a
setsid .venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --workers "$BACKEND_WORKERS" --log-level info > "$BACKEND_LOG" 2>&1 < /dev/null &
BACKEND_PID=$!

echo -e "${YELLOW}   Backend PID: $BACKEND_PID${NC}"

# Wait for backend to start
if wait_for_service $BACKEND_PORT "Backend"; then
    # Check backend health
    sleep 2
    if check_service_health $BACKEND_PORT "Backend" "http://localhost:$BACKEND_PORT/health"; then
        echo -e "${GREEN}🎉 Backend started successfully!${NC}"
        echo -e "   📚 API Docs: ${CYAN}http://localhost:$BACKEND_PORT/docs${NC}"
        echo -e "   🔍 Health: ${CYAN}http://localhost:$BACKEND_PORT/health${NC}"
    else
        echo -e "${YELLOW}⚠️  Backend started but health check failed${NC}"
    fi
else
    echo -e "${RED}❌ Backend failed to start${NC}"
    echo -e "${YELLOW}📋 Backend logs:${NC}"
    tail -20 "$BACKEND_LOG" || echo "No backend logs available"
    exit 1
fi

echo ""

# Build the frontend statically and let nginx serve frontend/dist directly.
# We used to run `npm run preview` here as a long-lived Node process on :8080,
# but `vite preview` is a single-threaded smoke-test server that re-validates
# every hashed asset.  Nginx serving the dist/ folder is faster, parallel, and
# leverages the immutable Cache-Control headers from the production site config.
# See PLAN.md (root) §1.
echo -e "${PURPLE}🎨 Building Frontend (static, served by nginx)...${NC}"
echo -e "   Output: ${CYAN}$PROJECT_ROOT/frontend/dist${NC}"
echo -e "   Log: ${CYAN}$FRONTEND_LOG${NC}"

cd "$PROJECT_ROOT/frontend"

echo -e "${YELLOW}🏗️  Building frontend bundle (npm run build)...${NC}"
if ! npm run build > "$FRONTEND_LOG" 2>&1; then
    echo -e "${RED}❌ Frontend build failed${NC}"
    echo -e "${YELLOW}📋 Build logs:${NC}"
    tail -40 "$FRONTEND_LOG" || echo "No build logs available"
    exit 1
fi
chmod -R a+rX "$PROJECT_ROOT/frontend/dist"
echo -e "${GREEN}✅ Frontend build completed${NC}"
FRONTEND_PID="(static, nginx-served)"

# Reload nginx so a fresh dist/ is picked up immediately (it's normally
# transparent because Vite emits content-hashed filenames, but reloading
# also flushes any open keepalive connections to the old origin).
if command -v nginx >/dev/null 2>&1; then
    if nginx -t >/dev/null 2>&1; then
        nginx -s reload >/dev/null 2>&1 || true
        echo -e "${GREEN}🔁 nginx reloaded${NC}"
    else
        echo -e "${YELLOW}⚠️  nginx -t failed; skipping reload${NC}"
    fi
fi

# Warm cache-friendly homepage sidebar endpoints so the first real visitor
# does not pay the cold DB cost on /tasks/top and /tasks/trending. We hit
# the backend directly to warm Postgres buffers, then the public URL so
# Nginx's proxy_cache fills with the same key the frontend will request.
echo -e "${PURPLE}🔥 Warming homepage sidebar endpoints...${NC}"
WARM_URLS=(
    "http://localhost:${BACKEND_PORT}/api/v1/tasks/top?limit=8"
    "http://localhost:${BACKEND_PORT}/api/v1/tasks/trending?limit=8"
    "https://paperswithcode.co/api/v1/tasks/top?limit=8"
    "https://paperswithcode.co/api/v1/tasks/trending?limit=8"
)
for url in "${WARM_URLS[@]}"; do
    if curl -sS -o /dev/null --max-time 15 "$url" >/dev/null 2>&1; then
        echo -e "   ${GREEN}✓${NC} ${url}"
    else
        echo -e "   ${YELLOW}⚠${NC}  failed to warm ${url}"
    fi
done

echo ""
echo -e "${GREEN}🎉 All services started successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}📱 Frontend:${NC} https://paperswithcode.co (static, served by nginx from frontend/dist)"
echo -e "${GREEN}🔧 Backend API:${NC} http://localhost:$BACKEND_PORT"
echo -e "${GREEN}📚 API Docs:${NC} http://localhost:$BACKEND_PORT/docs"
echo -e "${GREEN}🔍 Health Check:${NC} http://localhost:$BACKEND_PORT/health"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}📋 Process Information:${NC}"
echo -e "   Backend PID: ${CYAN}$BACKEND_PID${NC}"
echo -e "   Frontend PID: ${CYAN}$FRONTEND_PID${NC}"
echo ""
echo -e "${YELLOW}📁 Log Files:${NC}"
echo -e "   Backend: ${CYAN}$BACKEND_LOG${NC}"
echo -e "   Frontend: ${CYAN}$FRONTEND_LOG${NC}"
echo ""
echo -e "${YELLOW}🛑 To stop services:${NC}"
echo -e "   Run: ${CYAN}./stop_services.sh${NC}"
echo ""

# Only monitor in monitor mode
if [ "$MONITOR_MODE" = true ]; then
    echo -e "${BLUE}🔍 Monitoring services... (Press Ctrl+C to stop)${NC}"
    echo -e "${YELLOW}   Use 'tail -f $BACKEND_LOG' to monitor backend logs${NC}"
    echo -e "${YELLOW}   Use 'tail -f $FRONTEND_LOG' to monitor frontend logs${NC}"
    echo ""

    # Keep script running to maintain processes
    while true; do
        # Backend is the only managed long-running process now; nginx serves
        # the frontend directly from frontend/dist.
        if ! kill -0 $BACKEND_PID 2>/dev/null; then
            echo -e "${RED}❌ Backend process died (PID: $BACKEND_PID)${NC}"
            echo -e "${YELLOW}📋 Recent backend logs:${NC}"
            tail -10 "$BACKEND_LOG" || echo "No backend logs available"
            break
        fi

        sleep 10
    done

    echo -e "${YELLOW}🛑 Service monitoring stopped${NC}"
else
    echo -e "${GREEN}✨ Services are running in the background!${NC}"
    echo -e "${YELLOW}   They will continue running after you disconnect from SSH.${NC}"
    echo ""
    echo -e "${YELLOW}📋 To monitor logs:${NC}"
    echo -e "   Backend:  ${CYAN}tail -f $BACKEND_LOG${NC}"
    echo -e "   Frontend: ${CYAN}tail -f $FRONTEND_LOG${NC}"
fi
