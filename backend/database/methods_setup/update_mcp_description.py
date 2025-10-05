#!/usr/bin/env python3
"""
Update the MCP (Model Context Protocol) method description in the database.

This script updates the MCP method with a comprehensive description based on
the official Model Context Protocol documentation.

Usage:
    uv run --env-file backend/keys.env backend/database/methods_setup/update_mcp_description.py
"""

import sys
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def get_db_connection():
    """Get database connection using environment variables."""
    db_params = {
        "dbname": os.getenv("DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    return psycopg2.connect(**db_params)


def update_mcp_description():
    """Update the MCP method description in the database."""

    # Comprehensive description based on official MCP documentation
    mcp_description = """Model Context Protocol (MCP) is an open-source standard for connecting AI applications to external systems. MCP provides a standardized way to connect AI applications like Claude or ChatGPT to data sources (e.g., local files, databases), tools (e.g., search engines, calculators), and workflows (e.g., specialized prompts)—enabling them to access key information and perform tasks.

Think of MCP like a USB-C port for AI applications: just as USB-C provides a standardized way to connect electronic devices, MCP provides a standardized way to connect AI applications to external systems.

Key capabilities enabled by MCP include:
- Agents can access calendars and note-taking apps, acting as personalized AI assistants
- AI can generate entire web applications using design files
- Enterprise chatbots can connect to multiple databases across an organization
- AI models can create 3D designs and control hardware devices

MCP reduces development time and complexity when building or integrating with AI applications, provides access to an ecosystem of data sources and tools, and results in more capable AI applications that can access user data and take actions when necessary."""

    conn = get_db_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First, check if MCP method exists
            cur.execute(
                "SELECT id, name, description, full_name FROM methods WHERE name = %s",
                ("MCP",),
            )
            method = cur.fetchone()

            if not method:
                print("❌ MCP method not found in database")
                print("\nSearching for similar methods...")
                cur.execute(
                    "SELECT id, name FROM methods WHERE name ILIKE %s ORDER BY name",
                    ("%MCP%",),
                )
                similar = cur.fetchall()
                if similar:
                    print("Similar methods found:")
                    for m in similar:
                        print(f"  - ID {m['id']}: {m['name']}")
                else:
                    print("  No similar methods found")
                return

            print(f"✓ Found MCP method (ID: {method['id']})")
            print(f"  Current name: {method['name']}")
            print(f"  Current full_name: {method['full_name']}")
            print(
                f"  Current description: {method['description'][:100] if method['description'] else 'None'}..."
            )

            # Update the method
            cur.execute(
                """
                UPDATE methods
                SET
                    full_name = %s,
                    description = %s,
                    source_url = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = %s
                RETURNING id, name, full_name
                """,
                (
                    "Model Context Protocol",
                    mcp_description,
                    "https://modelcontextprotocol.io/docs/getting-started/intro",
                    "MCP",
                ),
            )

            updated = cur.fetchone()
            conn.commit()

            print("\n✅ Successfully updated MCP method!")
            print(f"  ID: {updated['id']}")
            print(f"  Name: {updated['name']}")
            print(f"  Full Name: {updated['full_name']}")
            print(f"  Description length: {len(mcp_description)} characters")
            print(
                "  Source URL: https://modelcontextprotocol.io/docs/getting-started/intro"
            )

    except Exception as e:
        print(f"\n❌ Error updating MCP method: {str(e)}")
        import traceback

        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    update_mcp_description()
