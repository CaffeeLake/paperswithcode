#!/bin/bash

# PapersWithCode Services Startup Script
# Manages both backend (FastAPI) and frontend (Vite) services
# Includes process cleanup, health checks, and proper logging

set -e  # Exit on any error

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
            sleep 2
            # Force kill if still running
            kill -KILL $pids 2>/dev/null || true
            sleep 1
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
        sleep 2
        # Force kill if still running
        pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            kill -KILL $pids 2>/dev/null || true
        fi
        sleep 1
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

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down services...${NC}"
    kill_port_processes $BACKEND_PORT "Backend"
    kill_port_processes $FRONTEND_PORT "Frontend"
    kill_processes_by_pattern "uvicorn.*backend.main:app" "Backend"
    kill_processes_by_pattern "vite" "Frontend"
    echo -e "${GREEN}✅ Cleanup completed${NC}"
}

# Set up signal handlers
trap cleanup EXIT INT TERM

echo -e "${PURPLE}🧹 Cleaning up existing processes...${NC}"

# Kill existing processes
kill_port_processes $BACKEND_PORT "Backend"
kill_port_processes $FRONTEND_PORT "Frontend"
kill_processes_by_pattern "uvicorn.*backend.main:app" "Backend"
kill_processes_by_pattern "vite" "Frontend"

echo -e "${GREEN}✅ Cleanup completed${NC}"
echo ""

# Change to project directory
cd "$PROJECT_ROOT"

# Start Backend
echo -e "${PURPLE}🔧 Starting Backend (FastAPI)...${NC}"
echo -e "   Environment: ${CYAN}backend/keys.env${NC}"
echo -e "   Port: ${CYAN}$BACKEND_PORT${NC}"
echo -e "   Log: ${CYAN}$BACKEND_LOG${NC}"

# Start backend in background with logging
nohup uv run --env-file backend/keys.env backend/run_server.py > "$BACKEND_LOG" 2>&1 &
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

# Start Frontend
echo -e "${PURPLE}🎨 Starting Frontend (Vite)...${NC}"
echo -e "   Port: ${CYAN}$FRONTEND_PORT${NC}"
echo -e "   Log: ${CYAN}$FRONTEND_LOG${NC}"

# Change to frontend directory and start
cd "$PROJECT_ROOT/frontend"

# Start frontend in background with logging
nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

echo -e "${YELLOW}   Frontend PID: $FRONTEND_PID${NC}"

# Wait for frontend to start
if wait_for_service $FRONTEND_PORT "Frontend"; then
    echo -e "${GREEN}🎉 Frontend started successfully!${NC}"
    echo -e "   🌐 App: ${CYAN}http://localhost:$FRONTEND_PORT${NC}"
else
    echo -e "${RED}❌ Frontend failed to start${NC}"
    echo -e "${YELLOW}📋 Frontend logs:${NC}"
    tail -20 "$FRONTEND_LOG" || echo "No frontend logs available"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 All services started successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}📱 Frontend:${NC} http://localhost:$FRONTEND_PORT"
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
echo -e "   Press ${CYAN}Ctrl+C${NC} or run: ${CYAN}./stop_services.sh${NC}"
echo ""

# Monitor services (optional - can be interrupted)
echo -e "${BLUE}🔍 Monitoring services... (Press Ctrl+C to stop)${NC}"
echo -e "${YELLOW}   Use 'tail -f $BACKEND_LOG' to monitor backend logs${NC}"
echo -e "${YELLOW}   Use 'tail -f $FRONTEND_LOG' to monitor frontend logs${NC}"
echo ""

# Keep script running to maintain processes
while true; do
    # Check if processes are still running
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Backend process died (PID: $BACKEND_PID)${NC}"
        echo -e "${YELLOW}📋 Recent backend logs:${NC}"
        tail -10 "$BACKEND_LOG" || echo "No backend logs available"
        break
    fi

    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Frontend process died (PID: $FRONTEND_PID)${NC}"
        echo -e "${YELLOW}📋 Recent frontend logs:${NC}"
        tail -10 "$FRONTEND_LOG" || echo "No frontend logs available"
        break
    fi

    sleep 10
done

echo -e "${YELLOW}🛑 Service monitoring stopped${NC}"
