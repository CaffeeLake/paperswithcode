# Environment consolidation audit — 2026-07-23

Pre-migration read-only capture:

- production FastAPI ran as root from the developer checkout on `:8000`;
- staging FastAPI ran as root from the same checkout on `:8001`;
- public staging used a checkout-backed Vite/HMR server on `:8081`;
- staging ordinary API, docs, health, and thumbnails referenced production
  `:8000`; its admin check alone referenced staging `:8001`;
- production nginx served
  `/root/python_projects/pwc-releases/current/frontend-dist` with an unbounded
  historical asset archive;
- `pwc-app.service` called the process-killing/building
  `start_services.sh` from the checkout;
- the PostgreSQL backup timer ran the checkout backup script as root;
- the curation sidecar on `:8002` also ran from the checkout;
- `/srv/paperswithcode`, `/etc/paperswithcode`, and
  `/var/lib/paperswithcode` did not yet exist;
- 3.5 GiB was free on the 75 GiB filesystem; the existing thumbnail mirror
  occupied 2.6 GiB, local database backups 1.1 GiB, checkout logs 72 MiB, and
  CRON logs 130 MiB.

The audit identified all four prohibited couplings: mutable-checkout runtime,
cross-environment API/auth routing, relative persistent paths, and a backup
whose provenance was the developer checkout.

Use `python deploy/topology_audit.py --json` and `pwc-status` for the final
machine-readable topology.
