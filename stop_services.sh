#!/bin/bash

# PapersWithCode Services Stop Script
# Gracefully stops both backend and frontend services

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8000
FRONTEND_PORT=8080

echo -e "${BLUE}🛑 PapersWithCode Services Stop Script${NC}"
echo -e "${BLUE}=====================================${NC}"

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
        echo -e "${YELLOW}🔄 Stopping $service_name on port $port...${NC}"
        local pids=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "${YELLOW}   Killing processes: $pids${NC}"
            # Graceful shutdown
            kill -TERM $pids 2>/dev/null || true
            sleep 3

            # Check if still running
            local remaining_pids=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null || true)
            if [ -n "$remaining_pids" ]; then
                echo -e "${YELLOW}   Force killing remaining processes: $remaining_pids${NC}"
                kill -KILL $remaining_pids 2>/dev/null || true
                sleep 1
            fi

            # Final check
            if check_port $port; then
                echo -e "${RED}   ❌ Failed to stop $service_name on port $port${NC}"
            else
                echo -e "${GREEN}   ✅ $service_name stopped successfully${NC}"
            fi
        fi
    else
        echo -e "${GREEN}✅ $service_name is not running on port $port${NC}"
    fi
}

# Function to kill processes by name pattern
kill_processes_by_pattern() {
    local pattern=$1
    local service_name=$2

    local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}🔄 Stopping $service_name processes...${NC}"
        echo -e "${YELLOW}   Killing processes: $pids${NC}"
        # Graceful shutdown
        kill -TERM $pids 2>/dev/null || true
        sleep 3

        # Check if still running
        local remaining_pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$remaining_pids" ]; then
            echo -e "${YELLOW}   Force killing remaining processes: $remaining_pids${NC}"
            kill -KILL $remaining_pids 2>/dev/null || true
            sleep 1
        fi

        # Final check
        local final_pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [ -n "$final_pids" ]; then
            echo -e "${RED}   ❌ Failed to stop some $service_name processes${NC}"
        else
            echo -e "${GREEN}   ✅ $service_name processes stopped successfully${NC}"
        fi
    else
        echo -e "${GREEN}✅ No $service_name processes found${NC}"
    fi
}

echo -e "${PURPLE}🧹 Stopping all PapersWithCode services...${NC}"
echo ""

# Stop Backend
echo -e "${YELLOW}🔧 Stopping Backend (FastAPI)...${NC}"
kill_port_processes $BACKEND_PORT "Backend"
kill_processes_by_pattern "uvicorn.*backend.main:app" "Backend (uvicorn)"
kill_processes_by_pattern "backend/run_server.py" "Backend (run_server)"

echo ""

# Stop Frontend
echo -e "${YELLOW}🎨 Stopping Frontend (Vite)...${NC}"
kill_port_processes $FRONTEND_PORT "Frontend"
kill_processes_by_pattern "vite preview" "Frontend (preview)"
kill_processes_by_pattern "vite( |$)" "Frontend (vite)"
kill_processes_by_pattern "npm run dev" "Frontend (npm dev)"
kill_processes_by_pattern "npm run preview" "Frontend (npm preview)"

echo ""

# Final status check
echo -e "${BLUE}📊 Final Status Check:${NC}"
if check_port $BACKEND_PORT; then
    echo -e "${RED}❌ Backend still running on port $BACKEND_PORT${NC}"
else
    echo -e "${GREEN}✅ Backend stopped (port $BACKEND_PORT free)${NC}"
fi

if check_port $FRONTEND_PORT; then
    echo -e "${RED}❌ Frontend still running on port $FRONTEND_PORT${NC}"
else
    echo -e "${GREEN}✅ Frontend stopped (port $FRONTEND_PORT free)${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Service shutdown completed!${NC}"
echo -e "${YELLOW}💡 To start services again, run: ${CYAN}./start_services.sh${NC}"
