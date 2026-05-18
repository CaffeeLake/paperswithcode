# Postgres Backup Cron Plan

## Goal

Create an automated off-VPS Postgres backup workflow for `paperswithcode.co`.

The backup should run on the VPS, create a compressed logical Postgres dump, upload it to a private Hugging Face Bucket, verify the upload, and prune old backups. The job should be simple enough to debug quickly before a launch.

## Why Local VPS Cron

Run the actual backup on the VPS, not GitHub Actions.

The database is local to the VPS, so a local cron/systemd timer can access Postgres without exposing the database publicly or storing SSH/database credentials in GitHub. GitHub Actions can later be used as an external monitor, but should not be the primary backup runner.

## Current Manual Backup

The first off-VPS backup was created and uploaded successfully:

```text
bucket: nielsr/paperswithcode-backups
path: postgres/paperswithcode_hf_20260518_091511.dump
checksum: postgres/paperswithcode_hf_20260518_091511.dump.sha256
private: true
remote size: ~139 MB
```

The application DB user did not have permission for one old backup table, so the full dump should run as the local `postgres` OS user.

## Backup Script

Add a script:

```text
scripts/backup_postgres_to_hf_bucket.sh
```

Responsibilities:

1. Load `backend/keys.env`.
2. Create `backups/postgres/` if missing.
3. Dump the database as the local `postgres` user:

```bash
sudo -u postgres pg_dump -d "$PWC_DB_NAME" -Fc -Z 9 -f "/tmp/$BACKUP_NAME"
```

4. Move the dump into `backups/postgres/`.
5. Create a SHA-256 checksum file.
6. Upload both files to:

```text
hf://buckets/nielsr/paperswithcode-backups/postgres/
```

7. List the remote bucket path and verify the uploaded filenames are present.
8. Run `sha256sum -c` locally.
9. Prune old local backups.
10. Prune old remote backups only after a successful upload.

Use `uv run --env-file backend/keys.env hf ...` so the repo-managed `huggingface_hub` CLI is used even if the standalone `hf` binary is not installed globally.

## Retention Policy

Start conservative:

- Keep the last `14` daily backups locally.
- Keep the last `30` daily backups remotely.

Current dump size is about `139 MB`, so `30` remote backups is roughly `4-5 GB` before database growth. This is acceptable for launch safety.

Pruning rule:

- Sort by timestamped filename.
- Delete oldest files beyond the retention count.
- Always delete `.dump` and matching `.dump.sha256` together.
- Never prune remote backups if the current upload or verification failed.

## Scheduling

Prefer systemd timers over crontab because logs and status are easier to inspect.

Create:

```text
/etc/systemd/system/pwc-postgres-backup.service
/etc/systemd/system/pwc-postgres-backup.timer
```

Service:

```ini
[Unit]
Description=PapersWithCode Postgres backup to Hugging Face Bucket

[Service]
Type=oneshot
WorkingDirectory=/root/python_projects/paperswithcode
ExecStart=/root/python_projects/paperswithcode/scripts/backup_postgres_to_hf_bucket.sh
```

Timer:

```ini
[Unit]
Description=Daily PapersWithCode Postgres backup

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl daemon-reload
systemctl enable --now pwc-postgres-backup.timer
```

Manual run:

```bash
systemctl start pwc-postgres-backup.service
```

Status and logs:

```bash
systemctl status pwc-postgres-backup.timer
systemctl status pwc-postgres-backup.service
journalctl -u pwc-postgres-backup.service -n 100 --no-pager
```

## Verification

Each run should print:

- Local dump path.
- Local dump size.
- Local checksum path.
- Remote bucket path.
- Remote listing confirmation.
- Local checksum verification result.
- Pruned local/remote filenames, if any.

Minimum health checks:

```bash
uv run --env-file backend/keys.env hf buckets info nielsr/paperswithcode-backups --format json
uv run --env-file backend/keys.env hf buckets list nielsr/paperswithcode-backups --recursive --human-readable
```

## Restore Drill

Before relying on the automation, document and test a restore path on a throwaway database.

Example:

```bash
createdb paperswithcode_restore_test
pg_restore -d paperswithcode_restore_test backups/postgres/<backup>.dump
psql -d paperswithcode_restore_test -c "select count(*) from papers;"
dropdb paperswithcode_restore_test
```

This verifies the dump is not just uploaded, but actually restorable.

## Failure Handling

The script should fail fast with `set -euo pipefail`.

Common failures:

- HF token missing or expired.
- Bucket permission issue.
- Disk full during dump.
- Postgres unavailable.
- Network failure during upload.

If a run fails:

1. Do not prune local or remote backups.
2. Leave the failed local dump in place only if it is non-empty and useful for debugging.
3. Check `journalctl -u pwc-postgres-backup.service`.
4. Re-run manually after fixing the issue.

## Optional Later Improvements

- Add encryption before upload with `age` or `gpg`.
- Add a GitHub Actions monitor that checks whether the bucket has a backup newer than `24h`.
- Send failure notifications to email, Slack, Discord, or a healthcheck URL.
- Store a weekly/monthly long-retention backup separately from daily backups.
