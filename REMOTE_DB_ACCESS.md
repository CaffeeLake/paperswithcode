# Quick Reference: Remote PostgreSQL Access

## 🚀 Adding Your IP to Access the Database

### Quick Command
```bash
sudo ./scripts/manage_postgres_access.sh add YOUR_IP paperswithcode_user paperswithcode_hf
```

**Example:**
```bash
sudo ./scripts/manage_postgres_access.sh add 84.198.172.145 paperswithcode_user paperswithcode_hf
```

This automatically:
- ✅ Configures PostgreSQL to listen on all interfaces
- ✅ Adds both SSL and non-SSL connection support
- ✅ Adds firewall rules for your IP
- ✅ Creates configuration backups
- ✅ Restarts/reloads PostgreSQL as needed

---

## 🔌 Connection Details

Once your IP is whitelisted, use these details in DataGrip/DBeaver/psql:

```
Host: 167.235.148.241
Port: 5432
Database: paperswithcode_hf
User: paperswithcode_user
Password: paperswithcode123
SSL: Optional (both SSL and non-SSL supported)
```

---

## 📋 Useful Commands

### List whitelisted IPs
```bash
./scripts/manage_postgres_access.sh list
```

### Remove an IP
```bash
sudo ./scripts/manage_postgres_access.sh remove 84.198.172.145
```

### Create backup
```bash
./scripts/manage_postgres_access.sh backup
```

### Test connection from terminal
```bash
psql -h 167.235.148.241 -p 5432 -U paperswithcode_user -d paperswithcode_hf
```

---

## 🔍 Example Queries

### View AI-extracted URLs
```sql
SELECT
    p.arxiv_id,
    p.title,
    r.url as github_url,
    r.source as github_source,
    pp.url as project_page_url,
    pp.source as project_page_source
FROM papers p
LEFT JOIN paper_repositories pr ON p.id = pr.paper_id AND pr.is_official = TRUE
LEFT JOIN repositories r ON pr.repository_id = r.id
LEFT JOIN paper_project_pages ppp ON p.id = ppp.paper_id
LEFT JOIN project_pages pp ON ppp.project_page_id = pp.id
WHERE r.source = 'ai_extraction' OR pp.source = 'ai_extraction'
ORDER BY p.date_published DESC
LIMIT 20;
```

### Check extraction statistics
```sql
SELECT
  COUNT(*) as total_papers,
  COUNT(DISTINCT CASE WHEN r.source = 'ai_extraction' THEN p.id END) as ai_github_urls,
  COUNT(DISTINCT CASE WHEN r.source = 'hf_api' THEN p.id END) as hf_github_urls,
  COUNT(DISTINCT CASE WHEN pp.source = 'ai_extraction' THEN p.id END) as ai_project_pages,
  COUNT(DISTINCT CASE WHEN pp.source = 'hf_api' THEN p.id END) as hf_project_pages
FROM papers p
LEFT JOIN paper_repositories pr ON p.id = pr.paper_id AND pr.is_official = TRUE
LEFT JOIN repositories r ON pr.repository_id = r.id
LEFT JOIN paper_project_pages ppp ON p.id = ppp.paper_id
LEFT JOIN project_pages pp ON ppp.project_page_id = pp.id
WHERE p.urls_extracted = TRUE;
```

### View recent papers
```sql
SELECT
    arxiv_id,
    title,
    date_published,
    citation_count,
    urls_extracted
FROM papers
ORDER BY date_published DESC
LIMIT 50;
```

---

## 🛠️ Troubleshooting

### Connection Refused
- **Check**: `sudo ufw status | grep 5432`
- **Fix**: Your IP might not be whitelisted in the firewall

### Authentication Failed
- **Check**: `sudo cat /etc/postgresql/16/main/pg_hba.conf | grep YOUR_IP`
- **Fix**: Re-run the management script

### Wrong Database Name
- **Common mistake**: Using `paperswithcode` instead of `paperswithcode_hf`
- **Fix**: Use `paperswithcode_hf` in connection string

---

## 📚 Full Documentation

For complete security documentation, see:
- [POSTGRES_SECURITY.md](docs/POSTGRES_SECURITY.md)
- [NETWORK_ARCHITECTURE.md](docs/NETWORK_ARCHITECTURE.md)

---

**Last Updated:** October 1, 2025
