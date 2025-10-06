#!/usr/bin/env python3
"""
Add DUSt3r method to the methods table if it doesn't exist.
"""

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get database connection using environment variables."""
    db_params = {
        "host": "localhost",
        "port": "5432",
        "database": "paperswithcode_hf",
        "user": "postgres",
        "password": "postgres",
    }

    return psycopg2.connect(**db_params)


def add_dust3r_method():
    """Add DUSt3r method to the methods table if it doesn't exist."""

    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if DUSt3r method already exists
            print("1. Checking if DUSt3r method exists...")
            cur.execute("SELECT id, name, full_name FROM methods WHERE name = 'DUSt3r'")
            method = cur.fetchone()

            if method:
                print(f"✓ DUSt3r method already exists (ID: {method['id']})")
                print(f"   Name: {method['name']}")
                if method["full_name"]:
                    print(f"   Full name: {method['full_name']}")
                return method["id"]

            # Add DUSt3r method
            print("\n2. Adding DUSt3r method to database...")
            cur.execute(
                """
                INSERT INTO methods (name, full_name, description, collection_name, collection_area)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    "DUSt3r",
                    "DUSt3r: Dense and Unconstrained Stereo 3D Reconstruction",
                    "A method for dense and unconstrained stereo 3D reconstruction from images",
                    "Computer Vision",
                    "3D Reconstruction",
                ),
            )

            method_id = cur.fetchone()["id"]
            conn.commit()

            print(f"✓ Added DUSt3r method with ID: {method_id}")
            print("   Name: DUSt3r")
            print(
                "   Full name: DUSt3r: Dense and Unconstrained Stereo 3D Reconstruction"
            )
            print(
                "   Description: A method for dense and unconstrained stereo 3D reconstruction from images"
            )
            print("   Collection: Computer Vision - 3D Reconstruction")

            return method_id

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Adding DUSt3r Method to Database")
    print("=" * 80)

    method_id = add_dust3r_method()
    print(f"\n✅ DUSt3r method ready with ID: {method_id}")
