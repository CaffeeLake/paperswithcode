# Database Access & Security

## Overview

- Engine: PostgreSQL 16 (`paperswithcode_hf` database)
- Default application role: `paperswithcode_user`
- Superuser (system managed): `postgres`
- Connection settings are loaded from `backend/keys.env`

Use `uv run --env-file backend/keys.env …` for any script that touches the database.

## Local Development Access

```bash
# Open psql as the application user
PGPASSWORD=$(grep PWC_DB_PASSWORD backend/keys.env | cut -d= -f2) \
  psql -h localhost -U paperswithcode_user -d paperswithcode_hf

# From Python
from backend.database.connection import get_database_session

with get_database_session() as db:
    papers = db.execute("SELECT id, arxiv_id FROM papers LIMIT 5").all()
```

## Remote Access (Whitelist Required)

The server allows remote connections only for explicit IPs using `scripts/manage_postgres_access.sh`.

```bash
# Add your public IP (requires sudo)
sudo ./scripts/manage_postgres_access.sh add 84.198.172.145 paperswithcode_user paperswithcode_hf

# Remove an IP
sudo ./scripts/manage_postgres_access.sh remove 84.198.172.145

# List current entries
./scripts/manage_postgres_access.sh list
```

After whitelisting, connect with:

```
Host: 167.235.148.241
Port: 5432
DB:   paperswithcode_hf
User: paperswithcode_user
Pass: paperswithcode123
SSL:  Optional (both host and hostssl rules exist)
```

> Rotate passwords promptly if this instance contains sensitive data.

## Security Posture

- `pg_hba.conf` contains per-IP `host` and `hostssl` entries for whitelisted addresses.
- UFW blocks port 5432 for everything except approved IPs.
- PostgreSQL listens on all interfaces (`listen_addresses='*'`) to support the whitelist.
- Check status:

```bash
sudo ufw status | grep 5432
sudo -u postgres psql -c "SELECT * FROM pg_hba_file_rules;"
sudo netstat -tlnp | grep 5432
```

## Common Operations

```bash
# Inspect active sessions
sudo -u postgres psql -c "SELECT pid, usename, client_addr, query FROM pg_stat_activity;"

# Run schema migrations or SQL files
uv run --env-file backend/keys.env python backend/database/papers_setup/add_hf_papers.py

# One-off update (example: set method image URL)
PGPASSWORD=paperswithcode123 psql -h localhost -U paperswithcode_user -d paperswithcode_hf \
  -c "UPDATE methods SET image_url = 'https://example.com/image.png' WHERE name ILIKE 'function calling';"

# Grant permissions after creating tables as postgres
sudo -u postgres psql -d paperswithcode_hf -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode_hf -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO paperswithcode_user;"
```

## Troubleshooting

| Issue | What to check |
| --- | --- |
| `permission denied for table …` | Table/sequence ownership; re-run GRANTs above. |
| `no pg_hba.conf entry` | Ensure your IP was added via the manage script and reload Postgres: `sudo systemctl reload postgresql`. |
| Connection refused | Confirm firewall rule exists and PostgreSQL is running: `sudo systemctl status postgresql`. |
| Password auth failed | Compare credentials with `backend/keys.env`; beware of stale `.pgpass`. |

## References

- Schema reference: `docs/DATABASE_SCHEMA_UML.md`
- Keyword automation scripts: `backend/database/{tasks_setup,methods_setup}/`
- Remote access helper: `scripts/manage_postgres_access.sh`

_Last updated: 7 November 2025_
