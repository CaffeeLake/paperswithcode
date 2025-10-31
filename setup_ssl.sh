#!/bin/bash

# PapersWithCode SSL Certificate Setup Script
# This script obtains and configures SSL certificates from Let's Encrypt

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

DOMAIN="paperswithcode.co"
EMAIL="admin@paperswithcode.co"  # Change this to your email

echo -e "${BLUE}🔒 PapersWithCode SSL Certificate Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Domain: ${CYAN}$DOMAIN${NC}"
echo ""

# Check if domain resolves to this server
echo -e "${YELLOW}🔍 Checking DNS configuration...${NC}"
SERVER_IP=$(curl -4 -s ifconfig.me)
DOMAIN_IPS=$(dig +short $DOMAIN A)

echo -e "Server IP: ${CYAN}$SERVER_IP${NC}"
echo -e "Domain IPs: ${CYAN}$DOMAIN_IPS${NC}"

if echo "$DOMAIN_IPS" | grep -q "$SERVER_IP"; then
    echo -e "${GREEN}✅ DNS is correctly configured!${NC}"
else
    echo -e "${RED}❌ WARNING: Domain does not point to this server!${NC}"
    echo -e "${YELLOW}Please update your DNS A record to point to: ${CYAN}$SERVER_IP${NC}"
    echo -e "${YELLOW}Current DNS points to: ${CYAN}$DOMAIN_IPS${NC}"
    echo ""
    echo -e "${YELLOW}After updating DNS, wait 5-10 minutes for propagation, then run this script again.${NC}"
    exit 1
fi

echo ""

# Check if Nginx is running
echo -e "${YELLOW}🔍 Checking Nginx status...${NC}"
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✅ Nginx is running${NC}"
else
    echo -e "${RED}❌ Nginx is not running${NC}"
    echo -e "${YELLOW}Starting Nginx...${NC}"
    sudo systemctl start nginx
fi

echo ""

# Check if certificate already exists
if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    echo -e "${YELLOW}⚠️  Certificate already exists for $DOMAIN${NC}"
    echo -e "${YELLOW}Do you want to renew it? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}🔄 Renewing certificate...${NC}"
        sudo certbot renew --nginx --force-renewal
    else
        echo -e "${YELLOW}Skipping certificate renewal${NC}"
    fi
else
    # Obtain SSL certificate
    echo -e "${YELLOW}🔒 Obtaining SSL certificate from Let's Encrypt...${NC}"
    echo -e "${YELLOW}This will:${NC}"
    echo -e "  1. Verify domain ownership"
    echo -e "  2. Obtain SSL certificate"
    echo -e "  3. Automatically configure Nginx for HTTPS"
    echo -e "  4. Set up automatic renewal"
    echo ""

    # Run certbot
    sudo certbot --nginx \
        -d $DOMAIN \
        -d www.$DOMAIN \
        --non-interactive \
        --agree-tos \
        --email $EMAIL \
        --redirect

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ SSL certificate obtained successfully!${NC}"
    else
        echo -e "${RED}❌ Failed to obtain SSL certificate${NC}"
        echo -e "${YELLOW}Common issues:${NC}"
        echo -e "  1. DNS not propagated yet (wait 5-10 minutes)"
        echo -e "  2. Port 80 not accessible from internet"
        echo -e "  3. Domain ownership verification failed"
        exit 1
    fi
fi

echo ""

# Test Nginx configuration
echo -e "${YELLOW}🔍 Testing Nginx configuration...${NC}"
sudo nginx -t

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Nginx configuration is valid${NC}"
else
    echo -e "${RED}❌ Nginx configuration has errors${NC}"
    exit 1
fi

echo ""

# Reload Nginx
echo -e "${YELLOW}🔄 Reloading Nginx...${NC}"
sudo systemctl reload nginx

echo ""
echo -e "${GREEN}🎉 SSL setup completed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}🌐 Your site is now available at:${NC}"
echo -e "   ${CYAN}https://$DOMAIN${NC}"
echo -e "   ${CYAN}https://www.$DOMAIN${NC}"
echo ""
echo -e "${GREEN}📚 API Documentation:${NC}"
echo -e "   ${CYAN}https://$DOMAIN/docs${NC}"
echo ""
echo -e "${GREEN}🔒 Certificate Details:${NC}"
sudo certbot certificates
echo ""
echo -e "${YELLOW}📝 Notes:${NC}"
echo -e "  - Certificates are automatically renewed by certbot timer"
echo -e "  - Check renewal status: ${CYAN}sudo certbot renew --dry-run${NC}"
echo -e "  - View certbot logs: ${CYAN}sudo journalctl -u certbot${NC}"
echo ""
