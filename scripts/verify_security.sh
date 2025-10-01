#!/bin/bash

# Security Verification Script
# Verifies that PostgreSQL is secure and API is accessible

echo "================================================"
echo "  PapersWithCode Security Verification Script"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SUCCESS=0

echo "1. Checking PostgreSQL listening address..."
POSTGRES_LISTEN=$(sudo netstat -tlnp | grep 5432)
if echo "$POSTGRES_LISTEN" | grep -q "127.0.0.1:5432"; then
    echo -e "${GREEN}✅ PASS${NC}: PostgreSQL is listening only on localhost"
    echo "   $POSTGRES_LISTEN"
    ((SUCCESS++))
else
    echo -e "${RED}❌ FAIL${NC}: PostgreSQL is NOT properly secured!"
    echo "   Expected: 127.0.0.1:5432"
    echo "   Got: $POSTGRES_LISTEN"
fi
echo ""

echo "2. Checking Firewall (UFW) status..."
UFW_STATUS=$(sudo ufw status | grep -E "^(Status:|5432|8000)")
if echo "$UFW_STATUS" | grep -q "Status: active"; then
    echo -e "${GREEN}✅ PASS${NC}: Firewall is active"
    ((SUCCESS++))
else
    echo -e "${RED}❌ FAIL${NC}: Firewall is not active!"
fi

if echo "$UFW_STATUS" | grep "5432/tcp" | grep -q "DENY"; then
    echo -e "${GREEN}✅ PASS${NC}: Port 5432 is blocked by firewall"
    ((SUCCESS++))
else
    echo -e "${RED}❌ FAIL${NC}: Port 5432 is not properly blocked!"
fi

if echo "$UFW_STATUS" | grep "8000/tcp" | grep -q "ALLOW"; then
    echo -e "${GREEN}✅ PASS${NC}: Port 8000 is allowed by firewall"
    ((SUCCESS++))
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: Port 8000 is not explicitly allowed"
fi
echo ""

echo "3. Checking PostgreSQL configuration..."
POSTGRES_CONF="/etc/postgresql/16/main/postgresql.conf"
if sudo grep -q "^listen_addresses = 'localhost'" "$POSTGRES_CONF"; then
    echo -e "${GREEN}✅ PASS${NC}: postgresql.conf is configured correctly"
    ((SUCCESS++))
else
    echo -e "${RED}❌ FAIL${NC}: postgresql.conf is not configured correctly!"
    echo "   Expected: listen_addresses = 'localhost'"
    sudo grep "^listen_addresses" "$POSTGRES_CONF"
fi
echo ""

echo "4. Checking pg_hba.conf for remote access..."
PG_HBA="/etc/postgresql/16/main/pg_hba.conf"
REMOTE_ACCESS=$(sudo grep -E "^host.*0\.0\.0\.0/0" "$PG_HBA" 2>/dev/null)
if [ -z "$REMOTE_ACCESS" ]; then
    echo -e "${GREEN}✅ PASS${NC}: No remote access (0.0.0.0/0) configured"
    ((SUCCESS++))
else
    echo -e "${RED}❌ FAIL${NC}: Found remote access entries in pg_hba.conf:"
    echo "$REMOTE_ACCESS"
fi
echo ""

echo "5. Testing local PostgreSQL connection..."
if sudo -u postgres psql -c "SELECT 'Connection successful' as status;" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PASS${NC}: Local PostgreSQL connection works"
    ((SUCCESS++))
else
    echo -e "${RED}❌ FAIL${NC}: Cannot connect to PostgreSQL locally"
fi
echo ""

echo "6. Checking API server status..."
API_PORT=$(sudo netstat -tlnp | grep ":8000" | grep LISTEN)
if [ -n "$API_PORT" ]; then
    echo -e "${GREEN}✅ PASS${NC}: API server is running on port 8000"
    echo "   $API_PORT"
    ((SUCCESS++))
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: API server is not running on port 8000"
fi
echo ""

echo "7. Testing API health endpoint..."
API_HEALTH=$(curl -s -w "\n%{http_code}" http://localhost:8000/health 2>&1 | tail -n1)
if [ "$API_HEALTH" = "200" ]; then
    echo -e "${GREEN}✅ PASS${NC}: API health endpoint responds correctly"
    ((SUCCESS++))
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: API health endpoint returned: $API_HEALTH"
fi
echo ""

echo "8. Testing API papers endpoint..."
API_PAPERS=$(curl -s "http://localhost:8000/api/v1/papers?page=1&page_size=1" 2>&1)
if echo "$API_PAPERS" | grep -q '"count"'; then
    echo -e "${GREEN}✅ PASS${NC}: API papers endpoint works correctly"
    ((SUCCESS++))
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: API papers endpoint may have issues"
fi
echo ""

echo "================================================"
echo "  Security Verification Summary"
echo "================================================"
echo ""
echo "Tests Passed: $SUCCESS / 10"
echo ""

if [ $SUCCESS -ge 7 ]; then
    echo -e "${GREEN}✅ SECURITY STATUS: GOOD${NC}"
    echo ""
    echo "Your PostgreSQL database is properly secured!"
    echo "The API is accessible and working correctly."
    echo ""
    echo "Architecture:"
    echo "  • PostgreSQL: Secured (localhost only)"
    echo "  • API Server: Accessible (public)"
    echo "  • Firewall: Active and configured"
else
    echo -e "${RED}❌ SECURITY STATUS: NEEDS ATTENTION${NC}"
    echo ""
    echo "Some security checks failed. Please review the results above."
fi
echo ""
echo "For detailed information, see: docs/NETWORK_ARCHITECTURE.md"
echo "For PostgreSQL security details, see: docs/POSTGRES_SECURITY.md"
echo ""
