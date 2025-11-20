#!/bin/bash
# Helper script to create Modal secret from backend/keys.env
# This saves you from manually copying environment variables

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "Modal Secret Creator"
echo "========================================"
echo ""

# Check if Modal is installed
if ! command -v modal &> /dev/null; then
    echo -e "${RED}✗${NC} Modal CLI not installed"
    echo "  Install with: pip install modal"
    exit 1
fi

# Check if Modal is authenticated
if ! modal token current &> /dev/null; then
    echo -e "${RED}✗${NC} Not authenticated with Modal"
    echo "  Run: modal token new"
    exit 1
fi

# Check if keys.env exists
if [ ! -f "../backend/keys.env" ]; then
    echo -e "${RED}✗${NC} backend/keys.env not found"
    exit 1
fi

echo "Loading environment variables from backend/keys.env..."
source ../backend/keys.env

# Get VPS public IP (or use default)
VPS_IP="${VPS_IP:-167.235.148.241}"

echo ""
echo "This will create/update a Modal secret named 'paperswithcode-db' with:"
echo "  - Database credentials (using $VPS_IP as host)"
echo "  - API keys from backend/keys.env"
echo ""
echo -e "${YELLOW}Warning: This will overwrite existing 'paperswithcode-db' secret if it exists${NC}"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Creating Modal secret..."

# Create the secret
modal secret create paperswithcode-db \
  PWC_DB_USER="$PWC_DB_USER" \
  PWC_DB_PASSWORD="$PWC_DB_PASSWORD" \
  PWC_DB_HOST="$VPS_IP" \
  PWC_DB_PORT="$PWC_DB_PORT" \
  PWC_DB_NAME="$PWC_DB_NAME" \
  PWC_OPENROUTER_API_KEY="$PWC_OPENROUTER_API_KEY" \
  PWC_SEMANTIC_SCHOLAR_API_KEY="$PWC_SEMANTIC_SCHOLAR_API_KEY" \
  SEMANTIC_SCHOLAR_API_KEY="$SEMANTIC_SCHOLAR_API_KEY" \
  PWC_HF_TOKEN="$PWC_HF_TOKEN" \
  HF_TOKEN="$HF_TOKEN" \
  PWC_GITHUB_TOKEN="$PWC_GITHUB_TOKEN" \
  PWC_GEMINI_API_KEY="$PWC_GEMINI_API_KEY" \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  PWC_DATALAB_API_KEY="$PWC_DATALAB_API_KEY" \
  EXA_API_KEY="$EXA_API_KEY" \
  PWC_ENVIRONMENT="$PWC_ENVIRONMENT" \
  PWC_ADMIN_API_TOKEN="$PWC_ADMIN_API_TOKEN"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓${NC} Modal secret 'paperswithcode-db' created successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Test database connection:"
    echo "     modal run modal/test_modal_db.py"
    echo ""
    echo "  2. Process a single paper:"
    echo "     modal run modal/parse_modal.py --arxiv-id 2201.03545"
else
    echo ""
    echo -e "${RED}✗${NC} Failed to create secret"
    echo "Try creating it manually via the Modal dashboard:"
    echo "  https://modal.com/secrets"
    exit 1
fi

echo ""
