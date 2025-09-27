#!/bin/bash

# PapersWithCode Services Status Check Script
# Quick status check for both backend and frontend services

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8000
FRONTEND_PORT=8080
PROJECT_ROOT="/root/python_projects/paperswithcode"
LOG_DIR="$PROJECT_ROOT/logs"

echo -e "${BLUE}📊 PapersWithCode Services Status${NC}"
echo -e "${BLUE}=================================${NC}"

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
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

# Check Backend
echo -e "${YELLOW}🔧 Backend Status:${NC}"
if check_port $BACKEND_PORT; then
    backend_pids=$(lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t 2>/dev/null || true)
    echo -e "   Status: ${GREEN}RUNNING${NC} (PID: $backend_pids)"
    echo -e "   Port: ${CYAN}$BACKEND_PORT${NC}"
    echo -e "   URL: ${CYAN}http://localhost:$BACKEND_PORT${NC}"

    # Health check
    if check_service_health $BACKEND_PORT "Backend API" "http://localhost:$BACKEND_PORT/health"; then
        echo -e "   Health: ${GREEN}HEALTHY${NC}"
    else
        echo -e "   Health: ${YELLOW}UNHEALTHY${NC}"
    fi

    echo -e "   API Docs: ${CYAN}http://localhost:$BACKEND_PORT/docs${NC}"
else
    echo -e "   Status: ${RED}NOT RUNNING${NC}"
    echo -e "   Port: ${RED}$BACKEND_PORT (free)${NC}"
fi

echo ""

# Check Frontend
echo -e "${YELLOW}🎨 Frontend Status:${NC}"
if check_port $FRONTEND_PORT; then
    frontend_pids=$(lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t 2>/dev/null || true)
    echo -e "   Status: ${GREEN}RUNNING${NC} (PID: $frontend_pids)"
    echo -e "   Port: ${CYAN}$FRONTEND_PORT${NC}"
    echo -e "   URL: ${CYAN}http://localhost:$FRONTEND_PORT${NC}"

    # Simple connectivity check
    if curl -s -f "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
        echo -e "   Health: ${GREEN}ACCESSIBLE${NC}"
    else
        echo -e "   Health: ${YELLOW}NOT ACCESSIBLE${NC}"
    fi
else
    echo -e "   Status: ${RED}NOT RUNNING${NC}"
    echo -e "   Port: ${RED}$FRONTEND_PORT (free)${NC}"
fi

echo ""

# Check log files
echo -e "${YELLOW}📁 Log Files:${NC}"
if [ -f "$LOG_DIR/backend.log" ]; then
    backend_log_size=$(stat -c%s "$LOG_DIR/backend.log" 2>/dev/null || echo "0")
    echo -e "   Backend Log: ${CYAN}$LOG_DIR/backend.log${NC} (${backend_log_size} bytes)"
else
    echo -e "   Backend Log: ${RED}Not found${NC}"
fi

if [ -f "$LOG_DIR/frontend.log" ]; then
    frontend_log_size=$(stat -c%s "$LOG_DIR/frontend.log" 2>/dev/null || echo "0")
    echo -e "   Frontend Log: ${CYAN}$LOG_DIR/frontend.log${NC} (${frontend_log_size} bytes)"
else
    echo -e "   Frontend Log: ${RED}Not found${NC}"
fi

echo ""

# Overall status
backend_running=false
frontend_running=false

if check_port $BACKEND_PORT; then
    backend_running=true
fi

if check_port $FRONTEND_PORT; then
    frontend_running=true
fi

echo -e "${BLUE}🎯 Overall Status:${NC}"
if $backend_running && $frontend_running; then
    echo -e "   ${GREEN}✅ All services are running${NC}"
    echo -e "   ${CYAN}🌐 Application ready at: http://localhost:$FRONTEND_PORT${NC}"
elif $backend_running && ! $frontend_running; then
    echo -e "   ${YELLOW}⚠️  Backend running, Frontend stopped${NC}"
    echo -e "   ${YELLOW}💡 Run: ./start_services.sh to start frontend${NC}"
elif ! $backend_running && $frontend_running; then
    echo -e "   ${YELLOW}⚠️  Frontend running, Backend stopped${NC}"
    echo -e "   ${YELLOW}💡 Run: ./start_services.sh to start backend${NC}"
else
    echo -e "   ${RED}❌ All services are stopped${NC}"
    echo -e "   ${YELLOW}💡 Run: ./start_services.sh to start all services${NC}"
fi

echo ""
echo -e "${YELLOW}🛠️  Available Commands:${NC}"
echo -e "   Start services: ${CYAN}./start_services.sh${NC}"
echo -e "   Stop services: ${CYAN}./stop_services.sh${NC}"
echo -e "   Check status: ${CYAN}./check_services.sh${NC}"
