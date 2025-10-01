# PostgreSQL Security Configuration

## Overview

This document describes the security configuration for PostgreSQL database access, including both local connections and secure remote access for authorized IPs.

**Security Model**:
- PostgreSQL is configured for **selective remote access** using IP whitelisting
- Only authorized IP addresses can connect to the database
- Both SSL and non-SSL connections are supported for client compatibility
- Firewall rules enforce IP-based access control
- The FastAPI backend (port 8000) remains publicly accessible for frontend connections

For a complete overview of the network architecture, see [NETWORK_ARCHITECTURE.md](NETWORK_ARCHITECTURE.md).

## Security Measures Implemented

### 1. Network Access Restrictions

**Before (VULNERABLE):**
- PostgreSQL was listening on all interfaces (`listen_addresses = '*'`)
- Database was accessible from **any** IP address (`0.0.0.0/0` in pg_hba.conf)
- Port 5432 was exposed to the internet without IP restrictions

**After (SECURE):**
- PostgreSQL listens on all interfaces (`listen_addresses = '*'`)
- Only **whitelisted IPs** can connect (enforced by both pg_hba.conf and firewall)
- Firewall blocks all IPs except explicitly allowed ones
- Both SSL and non-SSL connections supported for client compatibility

### 2. Configuration Changes

#### postgresql.conf
```ini
# PostgreSQL listens on all interfaces for selective remote access
listen_addresses = '*'
port = 5432
```

#### pg_hba.conf
```bash
# Removed dangerous wildcard entries:
# host    paperswithcode    postgres    0.0.0.0/0    md5  ❌ INSECURE
# host    paperswithcode_hf    paperswithcode_user    0.0.0.0/0    md5  ❌ INSECURE

# Local connections (always allowed):
local   all             postgres                                peer
local   all             all                                     peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256

# Whitelisted remote IPs (example - managed by script):
# Remote access for 84.198.172.145 (added 2025-10-01)
hostssl    paperswithcode_hf    paperswithcode_user    84.198.172.145/32    md5
host       paperswithcode_hf    paperswithcode_user    84.198.172.145/32    md5
```

### 3. Firewall Configuration

UFW (Uncomplicated Firewall) enforces IP-based access control:
- ✅ SSH (22/tcp) - ALLOW (all)
- ✅ HTTP (80/tcp) - ALLOW (all)
- ✅ HTTPS (443/tcp) - ALLOW (all)
- ✅ PostgreSQL (5432/tcp) - ALLOW from whitelisted IPs only
- ❌ PostgreSQL (5432/tcp) - DENY from all other IPs

Example firewall rules:
```bash
5432/tcp    ALLOW    84.198.172.145     # Whitelisted IP
5432/tcp    DENY     Anywhere           # Block all others
```

## Current Status

✅ **SECURE**: PostgreSQL uses IP whitelisting with firewall enforcement
✅ **FUNCTIONAL**: Local applications can connect without restrictions
✅ **ACCESSIBLE**: Authorized remote IPs can connect via SSL or non-SSL
✅ **PROTECTED**: Firewall blocks all unauthorized access attempts
✅ **AUDITABLE**: All access rules are documented and timestamped

## Adding Authorized Remote Access

### Using the Management Script (Recommended)

The provided script automatically handles all configuration steps:

```bash
# Add an IP to the whitelist
sudo ./scripts/manage_postgres_access.sh add 84.198.172.145 paperswithcode_user paperswithcode_hf

# What this does:
# ✅ Checks and updates listen_addresses if needed
# ✅ Adds both SSL and non-SSL entries to pg_hba.conf
# ✅ Configures firewall rules
# ✅ Creates configuration backup
# ✅ Reloads/restarts PostgreSQL as needed

# Remove an IP from the whitelist
sudo ./scripts/manage_postgres_access.sh remove 84.198.172.145

# List current whitelisted IPs
./scripts/manage_postgres_access.sh list

# Create a manual backup
./scripts/manage_postgres_access.sh backup
```

### Connection Details for Remote Clients

Once your IP is whitelisted, use these connection details in DataGrip, DBeaver, psql, etc.:

```
Host: 167.235.148.241
Port: 5432
Database: paperswithcode_hf
User: paperswithcode_user
Password: paperswithcode123
SSL: Optional (both SSL and non-SSL supported)
```

**Testing the connection from Terminal:**
```bash
psql -h 167.235.148.241 -p 5432 -U paperswithcode_user -d paperswithcode_hf
```

### Manual Configuration (Advanced)

If you prefer to manually edit the configuration:

1. **Ensure PostgreSQL listens on all interfaces:**
   ```bash
   sudo nano /etc/postgresql/16/main/postgresql.conf
   # Set: listen_addresses = '*'
   ```

2. **Edit pg_hba.conf:**
   ```bash
   sudo nano /etc/postgresql/16/main/pg_hba.conf
   ```

3. **Add specific IP entries (both SSL and non-SSL):**
   ```bash
   # Add at the end of the file
   # Remote access for YOUR_IP_ADDRESS (added YYYY-MM-DD)
   hostssl    paperswithcode_hf    paperswithcode_user    YOUR_IP_ADDRESS/32    md5
   host       paperswithcode_hf    paperswithcode_user    YOUR_IP_ADDRESS/32    md5
   ```

4. **Add firewall rule:**
   ```bash
   sudo ufw allow from YOUR_IP_ADDRESS to any port 5432 proto tcp
   ```

5. **Apply changes:**
   ```bash
   # First time: restart PostgreSQL to apply listen_addresses change
   sudo systemctl restart postgresql

   # Subsequent changes: reload is sufficient
   sudo systemctl reload postgresql
   ```

## Security Best Practices

### 1. Regular Security Audits
- Monitor PostgreSQL logs for unauthorized access attempts
- Review whitelisted IPs monthly: `./scripts/manage_postgres_access.sh list`
- Keep PostgreSQL updated: `sudo apt update && sudo apt upgrade postgresql`
- Check for failed connection attempts in logs

### 2. Access Management
- **Only whitelist IPs you trust and control**
- Use specific IP addresses (/32) rather than ranges
- Remove unused IPs promptly: `sudo ./scripts/manage_postgres_access.sh remove IP`
- Document why each IP is whitelisted
- For dynamic IPs, consider VPN or SSH tunneling instead

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

### Check PostgreSQL is listening on all interfaces:
```bash
sudo netstat -tlnp | grep 5432
# Should show: 0.0.0.0:5432 and :::5432 (listening on all interfaces)
```

### Test local connectivity:
```bash
sudo -u postgres psql -c "SELECT version();"
```

### Check firewall status:
```bash
sudo ufw status
```

### Verify firewall rules:
```bash
# Check UFW status
sudo ufw status | grep 5432

# Test from whitelisted IP (should succeed):
psql -h 167.235.148.241 -p 5432 -U paperswithcode_user -d paperswithcode_hf

# Test from non-whitelisted IP (should fail):
# Connection will be refused by firewall
```

## Incident Response

If you suspect unauthorized access:

1. **Immediate Actions:**
   ```bash
   # Remove all whitelisted IPs
   ./scripts/manage_postgres_access.sh list  # Note all IPs first
   sudo ./scripts/manage_postgres_access.sh remove IP_ADDRESS  # For each IP

   # Check current connections
   sudo -u postgres psql -c "SELECT * FROM pg_stat_activity WHERE client_addr IS NOT NULL;"

   # Review recent authentication attempts
   sudo grep -i "authentication\|connection\|FATAL" /var/log/postgresql/postgresql-16-main.log | tail -100

   # Check failed connection attempts
   sudo grep "FATAL" /var/log/postgresql/postgresql-16-main.log | grep "no pg_hba.conf entry"
   ```

2. **Investigation:**
   - Check PostgreSQL logs for suspicious activity and IP addresses
   - Review system logs: `sudo journalctl -u postgresql -n 200`
   - Audit database for unauthorized changes
   - Verify firewall rules: `sudo ufw status numbered`

3. **Recovery:**
   - Change all database passwords immediately
   - Review and update access controls
   - Re-whitelist only known IPs with current requirements
   - Consider enabling additional logging temporarily
   - Restore from clean backup if database integrity is compromised

## Troubleshooting

### Connection Refused
- **Symptom**: Client can't connect, gets "connection refused"
- **Check**: Firewall rules with `sudo ufw status | grep 5432`
- **Fix**: Ensure IP is whitelisted in firewall

### Authentication Failed
- **Symptom**: Connection reaches server but auth fails
- **Check**: `sudo cat /etc/postgresql/16/main/pg_hba.conf | grep YOUR_IP`
- **Fix**: Ensure pg_hba.conf has entries for your IP and database

### SSL Error
- **Symptom**: SSL-related connection errors
- **Check**: Ensure both `hostssl` and `host` entries exist in pg_hba.conf
- **Fix**: Run management script to add both entry types

### Can't Connect After Adding IP
- **Common causes**:
  1. PostgreSQL not restarted after first-time listen_addresses change
  2. Firewall rule not added
  3. Wrong database name (use `paperswithcode_hf` not `paperswithcode`)
  4. Password incorrect
- **Fix**: Re-run management script or follow manual steps carefully

## Current Whitelisted IPs

To view current whitelisted IPs:
```bash
./scripts/manage_postgres_access.sh list
```

**Active IPs:**
- `84.198.172.145` - Development workstation (added 2025-10-01)

---

**Last Updated:** October 1, 2025
**Security Status:** ✅ SECURED (IP Whitelisting Active)
**PostgreSQL Access:** Restricted to whitelisted IPs only
**Next Review:** Recommended monthly
