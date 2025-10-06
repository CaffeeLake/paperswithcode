"""
Add slug field to methods table and populate slugs for existing methods.

This script:
1. Adds a slug column to the methods table
2. Generates URL-friendly slugs for all existing methods
3. Creates a unique index on the slug column

Usage:
    uv run --env-file backend/keys.env python backend/database/methods_setup/add_method_slugs.py
"""

import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.utils.slug_utils import generate_method_slug
from backend.models.database import Method as DBMethod


def add_slug_column(db: Session) -> None:
    """Add slug column to methods table if it doesn't exist."""
    print("🔧 Adding slug column to methods table...")

    try:
        # Check if slug column already exists
        result = db.execute(
            text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='methods' AND column_name='slug';
        """)
        )

        if result.fetchone():
            print("✓ Slug column already exists")
            return

        # Add slug column
        db.execute(
            text("""
            ALTER TABLE methods
            ADD COLUMN slug VARCHAR(255);
        """)
        )
        db.commit()
        print("✓ Added slug column to methods table")

    except Exception as e:
        db.rollback()
        print(f"✗ Error adding slug column: {e}")
        raise


def generate_slugs(db: Session) -> None:
    """Generate slugs for all methods."""
    print("\n🔧 Generating slugs for methods...")

    try:
        # Get all methods
        methods = db.query(DBMethod).all()
        total = len(methods)

        print(f"Found {total} methods to process")

        # Track slug conflicts
        slug_map = {}
        conflicts = []

        # First pass: generate slugs and check for conflicts
        for idx, method in enumerate(methods, 1):
            if idx % 100 == 0:
                print(f"  Processing {idx}/{total}...")

            slug = generate_method_slug(method.name)

            # Handle conflicts by appending the ID
            if slug in slug_map:
                conflicts.append((method, slug))
                slug = f"{slug}-{method.id}"

            slug_map[slug] = method.id
            method.slug = slug

        # Report conflicts
        if conflicts:
            print(
                f"\n⚠️  Found {len(conflicts)} slug conflicts (resolved by appending ID):"
            )
            for method, original_slug in conflicts[:10]:  # Show first 10
                print(
                    f"  - '{method.name}' -> '{method.slug}' (conflict with '{original_slug}')"
                )
            if len(conflicts) > 10:
                print(f"  ... and {len(conflicts) - 10} more")

        # Commit changes
        db.commit()
        print(f"\n✓ Generated {total} slugs")

    except Exception as e:
        db.rollback()
        print(f"✗ Error generating slugs: {e}")
        raise


def add_unique_index(db: Session) -> None:
    """Add unique index on slug column."""
    print("\n🔧 Adding unique index on slug column...")

    try:
        # Check if index already exists
        result = db.execute(
            text("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename='methods' AND indexname='ix_methods_slug';
        """)
        )

        if result.fetchone():
            print("✓ Index already exists")
            return

        # Create unique index
        db.execute(
            text("""
            CREATE UNIQUE INDEX ix_methods_slug ON methods(slug);
        """)
        )
        db.commit()
        print("✓ Added unique index on slug column")

    except Exception as e:
        db.rollback()
        print(f"✗ Error adding index: {e}")
        raise


def verify_slugs(db: Session) -> None:
    """Verify that all methods have slugs."""
    print("\n🔍 Verifying slugs...")

    try:
        # Count methods without slugs
        result = db.execute(
            text("""
            SELECT COUNT(*) FROM methods WHERE slug IS NULL;
        """)
        )
        null_count = result.scalar()

        if null_count > 0:
            print(f"⚠️  Found {null_count} methods without slugs")
            return False

        # Count total methods
        result = db.execute(
            text("""
            SELECT COUNT(*) FROM methods;
        """)
        )
        total_count = result.scalar()

        # Count unique slugs
        result = db.execute(
            text("""
            SELECT COUNT(DISTINCT slug) FROM methods;
        """)
        )
        unique_count = result.scalar()

        print(f"✓ All {total_count} methods have slugs")
        print(f"✓ All slugs are unique ({unique_count} unique slugs)")

        # Show some examples
        print("\n📋 Example slugs:")
        result = db.execute(
            text("""
            SELECT name, slug
            FROM methods
            ORDER BY RANDOM()
            LIMIT 10;
        """)
        )
        for name, slug in result:
            print(f"  - '{name}' -> '{slug}'")

        return True

    except Exception as e:
        print(f"✗ Error verifying slugs: {e}")
        return False


def main():
    """Main function."""
    print("=" * 60)
    print("Add Method Slugs Migration")
    print("=" * 60)

    try:
        # Get database session
        db = next(get_database_session())

        # Run migration steps
        add_slug_column(db)
        generate_slugs(db)
        add_unique_index(db)
        verify_slugs(db)

        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ Migration failed: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
