#!/usr/bin/env python3
"""
Add keywords column to tasks table and populate it for OCR and Vision-Language Models.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from backend.config import get_settings


def add_keywords_column():
    """Add keywords column to tasks table."""

    settings = get_settings()

    try:
        engine = create_engine(settings.database_url)

        print("=" * 80)
        print("Adding Keywords Column to Tasks Table")
        print("=" * 80)

        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(
                text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'tasks'
                AND column_name = 'keywords'
            """)
            )

            if result.fetchone():
                print("\n✓ Keywords column already exists in tasks table")
            else:
                print("\n1. Adding keywords column to tasks table...")
                conn.execute(
                    text("""
                    ALTER TABLE tasks
                    ADD COLUMN keywords TEXT
                """)
                )
                conn.commit()
                print("   ✓ Column added successfully")

            # Update OCR keywords
            print("\n2. Setting keywords for OCR task...")
            ocr_keywords = (
                "OCR, optical-character recognition, optical character recognition"
            )

            result = conn.execute(
                text("""
                UPDATE tasks
                SET keywords = :keywords
                WHERE name = 'OCR'
                RETURNING id, name
            """),
                {"keywords": ocr_keywords},
            )

            row = result.fetchone()
            if row:
                print(f"   ✓ Updated OCR (ID: {row[0]})")
                print(f"     Keywords: {ocr_keywords}")
            else:
                print("   ⚠️  OCR task not found")

            # Update Vision-Language Models keywords
            print("\n3. Setting keywords for Vision-Language Models task...")
            vlm_keywords = "VLM, Vision-Language Model, vision language model, Multimodal Large Language Model, Multimodal LLM, MLLM, LVLM"

            result = conn.execute(
                text("""
                UPDATE tasks
                SET keywords = :keywords
                WHERE name = 'Vision-Language Models'
                RETURNING id, name
            """),
                {"keywords": vlm_keywords},
            )

            row = result.fetchone()
            if row:
                print(f"   ✓ Updated Vision-Language Models (ID: {row[0]})")
                print(f"     Keywords: {vlm_keywords}")
            else:
                print("   ⚠️  Vision-Language Models task not found")

            conn.commit()

        print("\n" + "=" * 80)
        print("Verification")
        print("=" * 80)

        # Verify the changes
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT id, name, keywords
                FROM tasks
                WHERE keywords IS NOT NULL
                ORDER BY name
            """)
            )

            rows = result.fetchall()
            if rows:
                print(f"\nTasks with keywords ({len(rows)}):")
                for row in rows:
                    print(f"\n  {row[1]} (ID: {row[0]}):")
                    print(f"    {row[2]}")
            else:
                print("\nNo tasks with keywords found")

        print("\n" + "=" * 80)
        print("✅ Keywords column added and populated successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    add_keywords_column()
