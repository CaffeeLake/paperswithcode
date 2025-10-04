"""
Example script demonstrating the Areas API endpoints.

This script shows how to use the areas endpoints to:
1. List all research areas
2. Get a specific area by ID
3. Search for areas by name
"""

import requests

BASE_URL = "http://localhost:8000/api/v1"


def list_areas(page=1, page_size=10):
    """List all research areas with pagination."""
    print(f"\n{'=' * 60}")
    print(f"Listing research areas (page {page}, {page_size} per page)")
    print("=" * 60)

    response = requests.get(
        f"{BASE_URL}/areas/", params={"page": page, "page_size": page_size}
    )

    if response.status_code == 200:
        data = response.json()
        print(f"Total areas: {data['count']}")
        print(f"Next page: {data['next_page']}")
        print(f"Previous page: {data['previous_page']}")
        print("\nAreas on this page:")
        for area in data["results"]:
            print(f"  - {area['id']}: {area['name']}")
            if area.get("description"):
                print(f"    Description: {area['description'][:100]}...")
        return data
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


def get_area(area_id):
    """Get a specific area by ID."""
    print(f"\n{'=' * 60}")
    print(f"Getting area with ID: {area_id}")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/areas/{area_id}")

    if response.status_code == 200:
        area = response.json()
        print(f"ID: {area['id']}")
        print(f"Name: {area['name']}")
        print(f"Description: {area.get('description', 'N/A')}")
        print(f"Created at: {area.get('created_at', 'N/A')}")
        print(f"Updated at: {area.get('updated_at', 'N/A')}")
        return area
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


def search_areas(query, page_size=10):
    """Search for areas by name."""
    print(f"\n{'=' * 60}")
    print(f"Searching areas with query: '{query}'")
    print("=" * 60)

    response = requests.get(
        f"{BASE_URL}/areas/", params={"q": query, "page_size": page_size}
    )

    if response.status_code == 200:
        data = response.json()
        print(f"Found {data['count']} matching areas:")
        for area in data["results"]:
            print(f"  - {area['id']}: {area['name']}")
        return data
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


def main():
    """Run example requests."""
    print("PapersWithCode Areas API Examples")
    print("=" * 60)
    print("Make sure the API server is running on http://localhost:8000")

    try:
        # 1. List areas
        areas_data = list_areas(page=1, page_size=5)

        # 2. Get a specific area (if we have results)
        if areas_data and areas_data["results"]:
            first_area_id = areas_data["results"][0]["id"]
            get_area(first_area_id)

        # 3. Search for areas
        search_areas("vision")
        search_areas("language")

        print("\n" + "=" * 60)
        print("✓ Examples completed successfully!")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to the API server.")
        print("Please make sure the server is running with:")
        print("  uv run --env-file backend/keys.env backend/run_server.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
