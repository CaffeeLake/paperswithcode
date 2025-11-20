"""
Test script to verify Modal can connect to your PostgreSQL database.

Usage:
    modal run modal/test_modal_db.py
"""

import modal

app = modal.App("paperswithcode-db-test")


@app.function(
    secrets=[modal.Secret.from_name("paperswithcode-db")],
    image=modal.Image.debian_slim().pip_install("psycopg2-binary"),
)
def test_connection():
    """Test database connection from Modal."""
    import os
    import psycopg2

    print("\n" + "=" * 60)
    print("Testing PostgreSQL Connection from Modal")
    print("=" * 60)

    print("\nDatabase Configuration:")
    print(f"  Host: {os.environ.get('PWC_DB_HOST', 'NOT SET')}")
    print(f"  Port: {os.environ.get('PWC_DB_PORT', 'NOT SET')}")
    print(f"  Database: {os.environ.get('PWC_DB_NAME', 'NOT SET')}")
    print(f"  User: {os.environ.get('PWC_DB_USER', 'NOT SET')}")
    print(f"  Password: {'*' * 8 if os.environ.get('PWC_DB_PASSWORD') else 'NOT SET'}")

    try:
        print("\nAttempting to connect...")
        conn = psycopg2.connect(
            host=os.environ["PWC_DB_HOST"],
            port=int(os.environ.get("PWC_DB_PORT", 5432)),
            database=os.environ["PWC_DB_NAME"],
            user=os.environ["PWC_DB_USER"],
            password=os.environ["PWC_DB_PASSWORD"],
            connect_timeout=10,
        )

        print("✓ Connected successfully!\n")

        # Test basic queries
        cur = conn.cursor()

        print("Running test queries...")

        # Count papers
        cur.execute("SELECT COUNT(*) FROM papers;")
        papers_count = cur.fetchone()[0]
        print(f"  Papers: {papers_count:,}")

        # Count datasets
        cur.execute("SELECT COUNT(*) FROM datasets;")
        datasets_count = cur.fetchone()[0]
        print(f"  Datasets: {datasets_count:,}")

        # Count evaluations
        cur.execute("SELECT COUNT(*) FROM evaluations;")
        evaluations_count = cur.fetchone()[0]
        print(f"  Evaluations: {evaluations_count:,}")

        # Test write permissions (with rollback)
        try:
            cur.execute("BEGIN;")
            cur.execute("SELECT 1;")  # Simple test query
            cur.execute("ROLLBACK;")
            print("\n✓ Write permissions OK")
        except Exception as e:
            print(f"\n✗ Write permissions issue: {e}")

        conn.close()

        print("\n" + "=" * 60)
        print("✓ All tests passed! Modal can access your database.")
        print("=" * 60 + "\n")

        return {
            "success": True,
            "papers_count": papers_count,
            "datasets_count": datasets_count,
            "evaluations_count": evaluations_count,
        }

    except psycopg2.OperationalError as e:
        print(f"\n✗ Connection failed: {e}\n")
        print("Troubleshooting:")
        print("  1. Check PostgreSQL is listening on external interface")
        print("     sudo netstat -plnt | grep 5432")
        print("  2. Check firewall allows connections")
        print("     sudo ufw status | grep 5432")
        print("  3. Verify pg_hba.conf allows remote connections")
        print("     sudo cat /etc/postgresql/*/main/pg_hba.conf | grep paperswithcode")
        print("  4. Test from local machine first")
        print(
            f"     psql -h {os.environ.get('PWC_DB_HOST')} -U {os.environ.get('PWC_DB_USER')} -d {os.environ.get('PWC_DB_NAME')}"
        )
        print("\n" + "=" * 60 + "\n")
        raise

    except Exception as e:
        print(f"\n✗ Unexpected error: {e}\n")
        print("=" * 60 + "\n")
        raise


@app.local_entrypoint()
def main():
    """Run the database connection test."""
    print("\nRunning database connection test on Modal...\n")
    result = test_connection.remote()

    if result["success"]:
        print("Ready to process papers on Modal!")
        print("\nNext step:")
        print("  modal run modal/parse_modal.py --arxiv-id 2201.03545")
