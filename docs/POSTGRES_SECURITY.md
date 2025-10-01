# PostgreSQL Security Configuration

## Overview

This document describes the security measures implemented to protect the PostgreSQL database from unauthorized access, following the BSI (German Federal Office for Information Security) security alert.

**Important**: The PostgreSQL database is now **only accessible locally** on the VPS. The FastAPI backend (port 8000) remains publicly accessible as it should be - this is the correct architecture. The frontend connects to the API, and the API connects to PostgreSQL locally.

For a complete overview of the network architecture, see [NETWORK_ARCHITECTURE.md](NETWORK_ARCHITECTURE.md).

## Security Measures Implemented

### 1. Network Access Restrictions

**Before (VULNERABLE):**
- PostgreSQL was listening on all interfaces (`listen_addresses = '*'`)
- Database was accessible from any IP address (`0.0.0.0/0` in pg_hba.conf)
- Port 5432 was exposed to the internet

**After (SECURE):**
- PostgreSQL only listens on localhost (`listen_addresses = 'localhost'`)
- Only local connections are allowed
- Firewall blocks external access to port 5432

### 2. Configuration Changes

#### postgresql.conf
```ini
# Changed from:
listen_addresses = '*'

# To:
listen_addresses = 'localhost'
```

#### pg_hba.conf
```bash
# Removed dangerous entries:
# host    paperswithcode    postgres    0.0.0.0/0    md5
# host    paperswithcode    paperswithcode_user    0.0.0.0/0    md5
# host    paperswithcode_hf    paperswithcode_user    0.0.0.0/0    md5

# Now only local connections are allowed:
local   all             all                                     peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
```

### 3. Firewall Configuration

UFW (Uncomplicated Firewall) is now active with the following rules:
- ✅ SSH (22/tcp) - ALLOW
- ✅ HTTP (80/tcp) - ALLOW
- ✅ HTTPS (443/tcp) - ALLOW
- ❌ PostgreSQL (5432/tcp) - DENY

## Current Status

✅ **SECURE**: PostgreSQL is no longer accessible from the internet
✅ **FUNCTIONAL**: Local applications can still connect to the database
✅ **PROTECTED**: Firewall blocks external access attempts

## Adding Authorized Remote Access

If you need to allow specific IP addresses to access the database, use the provided management script:

### Using the Management Script

```bash
# Add an IP to the whitelist
./scripts/manage_postgres_access.sh add 192.168.1.100 paperswithcode_user paperswithcode

# Remove an IP from the whitelist
./scripts/manage_postgres_access.sh remove 192.168.1.100

# List current whitelisted IPs
./scripts/manage_postgres_access.sh list

# Create a backup
./scripts/manage_postgres_access.sh backup
```

### Manual Configuration

If you prefer to manually edit the configuration:

1. **Edit pg_hba.conf:**
   ```bash
   sudo nano /etc/postgresql/16/main/pg_hba.conf
   ```

2. **Add specific IP entries:**
   ```bash
   # Add at the end of the file
   host    paperswithcode    paperswithcode_user    YOUR_IP_ADDRESS/32    md5
   ```

3. **Reload PostgreSQL:**
   ```bash
   sudo systemctl reload postgresql
   ```

4. **Update firewall (if needed):**
   ```bash
   # Only if you need to allow specific IPs through firewall
   sudo ufw allow from YOUR_IP_ADDRESS to any port 5432
   ```

## Security Best Practices

### 1. Regular Security Audits
- Monitor PostgreSQL logs for unauthorized access attempts
- Review whitelisted IPs regularly
- Keep PostgreSQL updated

### 2. Access Management
- Only whitelist IPs you trust
- Use specific IP addresses (/32) rather than ranges
- Remove unused IPs promptly

### 3. Monitoring
```bash
# Check current connections
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity;"

# Monitor logs
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

### 4. Backup Strategy
- Configuration backups are automatically created in `/etc/postgresql/16/main/backups/`
- Database backups should be stored securely off-site

## Verification Commands

### Check PostgreSQL is listening only locally:
```bash
sudo netstat -tlnp | grep 5432
# Should show: 127.0.0.1:5432 and ::1:5432 only
```

### Test local connectivity:
```bash
sudo -u postgres psql -c "SELECT version();"
```

### Check firewall status:
```bash
sudo ufw status
```

### Verify no external access:
```bash
# From external machine (should fail):
telnet YOUR_SERVER_IP 5432
```

## Incident Response

If you suspect unauthorized access:

1. **Immediate Actions:**
   ```bash
   # Block all external access
   sudo ufw deny 5432/tcp

   # Check current connections
   sudo -u postgres psql -c "SELECT * FROM pg_stat_activity;"

   # Review logs
   sudo grep -i "authentication\|connection" /var/log/postgresql/postgresql-16-main.log
   ```

2. **Investigation:**
   - Check PostgreSQL logs for suspicious activity
   - Review system logs for unauthorized access
   - Audit database for unauthorized changes

3. **Recovery:**
   - Change all database passwords
   - Review and update access controls
   - Restore from clean backup if necessary

## Contact Information

For security-related questions or incidents:
- BSI CERT-Bund: certbund@bsi.bund.de
- Original ticket number: [CB-Report#...] (from the security alert)

---

**Last Updated:** October 1, 2025
**Security Status:** ✅ SECURED
**Next Review:** Recommended monthly
