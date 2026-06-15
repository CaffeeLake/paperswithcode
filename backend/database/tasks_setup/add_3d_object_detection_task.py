#!/usr/bin/env python3
"""Add or update the 3D object detection task."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIGRATION = Path("backend/database/migrations/add_3d_object_detection_task.sql")


def main() -> None:
    sql = MIGRATION.read_text()
    with db_manager.engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied %s", MIGRATION)


if __name__ == "__main__":
    main()
