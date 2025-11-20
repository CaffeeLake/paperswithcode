#!/bin/bash
# Modal deployment setup checker
# This script validates your environment before deploying to Modal

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "Modal Deployment Setup Checker"
echo "========================================"
echo ""

# Check if Modal is installed
echo -n "Checking Modal installation... "
if command -v modal &> /dev/null; then
    echo -e "${GREEN}✓${NC} Modal CLI found"
    modal --version
else
    echo -e "${RED}✗${NC} Modal not installed"
    echo "  Install with: pip install modal"
    exit 1
fi

echo ""

# Check if Modal is authenticated
echo -n "Checking Modal authentication... "
if modal token current &> /dev/null; then
    echo -e "${GREEN}✓${NC} Authenticated"
else
    echo -e "${RED}✗${NC} Not authenticated"
    echo "  Run: modal token new"
    exit 1
fi

echo ""

# Check if secret exists
echo -n "Checking Modal secret 'paperswithcode-db'... "
if modal secret list 2>&1 | grep -q "paperswithcode-db"; then
    echo -e "${GREEN}✓${NC} Secret exists"
else
    echo -e "${YELLOW}!${NC} Secret not found"
    echo "  Create it at: https://modal.com/secrets"
    echo "  Or use: modal secret create paperswithcode-db PWC_DB_USER=... PWC_DB_PASSWORD=..."
fi

echo ""

# Check if backend/keys.env exists
echo -n "Checking backend/keys.env file... "
if [ -f "../backend/keys.env" ]; then
    echo -e "${GREEN}✓${NC} File exists"

    # Check for required environment variables
    required_vars=(
        "PWC_DB_USER"
        "PWC_DB_PASSWORD"
        "PWC_DB_HOST"
        "PWC_DB_NAME"
        "PWC_OPENROUTER_API_KEY"
        "PWC_SEMANTIC_SCHOLAR_API_KEY"
        "PWC_HF_TOKEN"
        "PWC_GITHUB_TOKEN"
    )

    optional_vars=(
        "PWC_GEMINI_API_KEY"
        "OPENAI_API_KEY"
        "PWC_DATALAB_API_KEY"
        "EXA_API_KEY"
    )

    echo ""
    echo "Checking required environment variables:"
    for var in "${required_vars[@]}"; do
        if grep -q "^$var=" ../backend/keys.env; then
            echo -e "  ${GREEN}✓${NC} $var"
        else
            echo -e "  ${RED}✗${NC} $var (missing)"
        fi
    done

    echo ""
    echo "Checking optional environment variables:"
    for var in "${optional_vars[@]}"; do
        if grep -q "^$var=" ../backend/keys.env; then
            echo -e "  ${GREEN}✓${NC} $var"
        else
            echo -e "  ${YELLOW}!${NC} $var (not set)"
        fi
    done
else
    echo -e "${RED}✗${NC} File not found"
    echo "  Expected at: ../backend/keys.env"
fi

echo ""

# Check PostgreSQL connectivity from local machine
echo -n "Checking PostgreSQL local connectivity... "
if command -v psql &> /dev/null; then
    # Try to get connection info from keys.env
    if [ -f "../backend/keys.env" ]; then
        source ../backend/keys.env

        if [ ! -z "$PWC_DB_HOST" ] && [ ! -z "$PWC_DB_USER" ] && [ ! -z "$PWC_DB_NAME" ]; then
            # Test connection (with 3 second timeout)
            if PGPASSWORD="$PWC_DB_PASSWORD" psql -h "$PWC_DB_HOST" -U "$PWC_DB_USER" -d "$PWC_DB_NAME" -c "SELECT 1;" &> /dev/null; then
                echo -e "${GREEN}✓${NC} Can connect to database"
            else
                echo -e "${RED}✗${NC} Cannot connect to database"
                echo "  Host: $PWC_DB_HOST"
                echo "  User: $PWC_DB_USER"
                echo "  Database: $PWC_DB_NAME"
                echo ""
                echo "  Troubleshooting:"
                echo "  1. Check PostgreSQL is running: sudo systemctl status postgresql"
                echo "  2. Check firewall: sudo ufw status | grep 5432"
                echo "  3. Check pg_hba.conf allows remote connections"
            fi
        else
            echo -e "${YELLOW}!${NC} Missing database configuration in keys.env"
        fi
    fi
else
    echo -e "${YELLOW}!${NC} psql not installed, skipping"
fi

echo ""

# Check if parse_modal.py exists
echo -n "Checking parse_modal.py... "
if [ -f "parse_modal.py" ]; then
    echo -e "${GREEN}✓${NC} File exists"
else
    echo -e "${RED}✗${NC} File not found"
    echo "  Expected at: modal/parse_modal.py"
fi

echo ""

# Check if sample ArXiv IDs file exists
echo -n "Checking arxiv_ids_sample.txt... "
if [ -f "arxiv_ids_sample.txt" ]; then
    echo -e "${GREEN}✓${NC} File exists"
    num_lines=$(grep -v "^#" arxiv_ids_sample.txt | grep -v "^$" | wc -l)
    echo "  Contains $num_lines ArXiv IDs"
else
    echo -e "${YELLOW}!${NC} Sample file not found"
    echo "  Create one at: modal/arxiv_ids_sample.txt"
fi

echo ""
echo "========================================"
echo "Setup Check Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Test database connection:"
echo "     modal run modal/test_modal_db.py"
echo ""
echo "  2. Process a single paper:"
echo "     modal run modal/parse_modal.py --arxiv-id 2201.03545"
echo ""
echo "  3. Process a batch:"
echo "     modal run modal/parse_modal.py --batch modal/arxiv_ids_sample.txt"
echo ""
echo "For detailed setup instructions, see:"
echo "  modal/MODAL_SETUP.md"
echo ""
