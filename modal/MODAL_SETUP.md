# Modal Deployment Setup

This guide explains how to deploy the evaluation extraction pipeline to Modal for scalable processing of thousands of papers.

## Overview

Modal is a serverless platform designed for Python workloads. It allows you to run the extraction pipeline at massive scale without managing infrastructure.

**Benefits:**
- Process 100+ papers in parallel
- Pay only for compute time used (~$0.12 per paper)
- Automatic retries and error handling
- Built-in monitoring and logging
- No infrastructure management

## Prerequisites

- Modal account (free tier available at [modal.com](https://modal.com))
- Access to your PostgreSQL database from the internet
- Environment variables from `backend/keys.env`

## Step 1: Install Modal

```bash
pip install modal
```

## Step 2: Authenticate with Modal

```bash
modal token new
```

This will open your browser to authenticate with Modal. Follow the prompts to complete authentication.

## Step 3: Create Modal Secret

You need to create a secret in Modal containing your environment variables:

### Option A: Via Modal Dashboard (Recommended)

1. Go to [modal.com/secrets](https://modal.com/secrets)
2. Click "Create Secret"
3. Name it: `paperswithcode-db`
4. Add the following environment variables from your `backend/keys.env`:

```
# Database Configuration (REQUIRED)
PWC_DB_USER=paperswithcode_user
PWC_DB_PASSWORD=your_password
PWC_DB_HOST=167.235.148.241
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode_hf

# API Keys (REQUIRED)
PWC_OPENROUTER_API_KEY=sk-or-v1-your_openrouter_key
PWC_SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key
PWC_HF_TOKEN=hf_your_huggingface_token
HF_TOKEN=hf_your_huggingface_token
PWC_GITHUB_TOKEN=ghp_your_github_token

# Additional API Keys (OPTIONAL - if used by extraction pipeline)
PWC_GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=sk-proj-your_openai_key
PWC_DATALAB_API_KEY=your_datalab_key
EXA_API_KEY=your_exa_key

# Environment Configuration (OPTIONAL)
PWC_ENVIRONMENT=production
PWC_ADMIN_API_TOKEN=your_admin_token
```

**Note**: The extraction pipeline primarily uses:
- **OpenRouter** for AI-powered extraction
- **Semantic Scholar** for citation data
- **Hugging Face** for paper metadata
- **GitHub** for repository information

The optional keys may be needed depending on which features you're using.

### Option B: Via Modal CLI

```bash
# Create secret with all required environment variables
modal secret create paperswithcode-db \
  PWC_DB_USER=paperswithcode_user \
  PWC_DB_PASSWORD=your_password \
  PWC_DB_HOST=167.235.148.241 \
  PWC_DB_PORT=5432 \
  PWC_DB_NAME=paperswithcode_hf \
  PWC_OPENROUTER_API_KEY=sk-or-v1-your_openrouter_key \
  PWC_SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key \
  SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key \
  PWC_HF_TOKEN=hf_your_huggingface_token \
  HF_TOKEN=hf_your_huggingface_token \
  PWC_GITHUB_TOKEN=ghp_your_github_token \
  PWC_GEMINI_API_KEY=your_gemini_key \
  OPENAI_API_KEY=sk-proj-your_openai_key \
  PWC_DATALAB_API_KEY=your_datalab_key \
  EXA_API_KEY=your_exa_key \
  PWC_ENVIRONMENT=production \
  PWC_ADMIN_API_TOKEN=your_admin_token
```

**Pro tip**: You can also load all variables from your `backend/keys.env` file:

```bash
# From the project root directory
cd /root/python_projects/paperswithcode
source backend/keys.env

# Then create the secret (update PWC_DB_HOST to VPS IP)
modal secret create paperswithcode-db \
  PWC_DB_USER=$PWC_DB_USER \
  PWC_DB_PASSWORD=$PWC_DB_PASSWORD \
  PWC_DB_HOST=167.235.148.241 \
  PWC_DB_PORT=$PWC_DB_PORT \
  PWC_DB_NAME=$PWC_DB_NAME \
  PWC_OPENROUTER_API_KEY=$PWC_OPENROUTER_API_KEY \
  PWC_SEMANTIC_SCHOLAR_API_KEY=$PWC_SEMANTIC_SCHOLAR_API_KEY \
  SEMANTIC_SCHOLAR_API_KEY=$SEMANTIC_SCHOLAR_API_KEY \
  PWC_HF_TOKEN=$PWC_HF_TOKEN \
  HF_TOKEN=$HF_TOKEN \
  PWC_GITHUB_TOKEN=$PWC_GITHUB_TOKEN \
  PWC_GEMINI_API_KEY=$PWC_GEMINI_API_KEY \
  OPENAI_API_KEY=$OPENAI_API_KEY \
  PWC_DATALAB_API_KEY=$PWC_DATALAB_API_KEY \
  EXA_API_KEY=$EXA_API_KEY \
  PWC_ENVIRONMENT=$PWC_ENVIRONMENT \
  PWC_ADMIN_API_TOKEN=$PWC_ADMIN_API_TOKEN
```

## Step 4: Configure PostgreSQL Access

Your PostgreSQL database needs to accept connections from Modal workers.

### Security Warning ⚠️

Opening PostgreSQL to the internet has security implications. For production use, consider:
- Using a managed PostgreSQL service (DigitalOcean, AWS RDS, Supabase)
- Setting up SSH tunneling
- Using a VPN connection
- Adding IP whitelisting if Modal provides static IPs

### Basic Configuration (Development/Testing)

On your VPS:

```bash
# 1. Edit PostgreSQL configuration
sudo nano /etc/postgresql/*/main/postgresql.conf

# Find and change:
listen_addresses = 'localhost'
# To:
listen_addresses = '*'

# 2. Edit pg_hba.conf to allow remote connections
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Add at the end:
host    paperswithcode_hf    paperswithcode_user    0.0.0.0/0    md5

# 3. Open firewall port
sudo ufw allow 5432/tcp

# 4. Restart PostgreSQL
sudo systemctl restart postgresql

# 5. Test connection from your local machine
psql -h 167.235.148.241 -U paperswithcode_user -d paperswithcode_hf
```

### Enhanced Security (Production)

For production, add SSL requirement:

```bash
# In pg_hba.conf, use:
hostssl    paperswithcode_hf    paperswithcode_user    0.0.0.0/0    md5

# In postgresql.conf, enable SSL:
ssl = on
ssl_cert_file = '/etc/ssl/certs/ssl-cert-snakeoil.pem'
ssl_key_file = '/etc/ssl/private/ssl-cert-snakeoil.key'
```

Then in your Modal secret, add:
```
PWC_DB_SSLMODE=require
```

## Step 5: Test Connection

Test that Modal can connect to your database:

```python
# test_modal_db.py
import modal

app = modal.App("db-test")

@app.function(
    secrets=[modal.Secret.from_name("paperswithcode-db")]
)
def test_connection():
    import os
    import psycopg2

    print("Testing database connection...")
    print(f"Host: {os.environ['PWC_DB_HOST']}")
    print(f"Database: {os.environ['PWC_DB_NAME']}")
    print(f"User: {os.environ['PWC_DB_USER']}")

    try:
        conn = psycopg2.connect(
            host=os.environ["PWC_DB_HOST"],
            database=os.environ["PWC_DB_NAME"],
            user=os.environ["PWC_DB_USER"],
            password=os.environ["PWC_DB_PASSWORD"],
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM papers;")
        count = cur.fetchone()[0]
        print(f"✓ Successfully connected! Papers in database: {count}")
        conn.close()
        return "Success!"
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        raise

if __name__ == "__main__":
    with app.run():
        test_connection.remote()
```

Run:
```bash
modal run test_modal_db.py
```

## Step 6: Run Your First Paper

Test with a single paper:

```bash
cd /root/python_projects/paperswithcode
modal run modal/parse_modal.py --arxiv-id 2201.03545
```

This will:
1. Upload your code to Modal
2. Build a container with dependencies
3. Run the extraction pipeline on Modal's infrastructure
4. Stream logs back to your terminal
5. Print results when complete

## Step 7: Process a Batch

Create a file with ArXiv IDs (one per line):

```bash
# Create arxiv_ids.txt
cat > arxiv_ids.txt << EOF
2201.03545
2406.09414
2104.14294
2505.14683
EOF
```

Process the batch:

```bash
modal run modal/parse_modal.py \
  --batch arxiv_ids.txt \
  --max-workers 20
```

This will process up to 20 papers in parallel.

## Usage Examples

### Single Paper (with resume)
```bash
modal run modal/parse_modal.py --arxiv-id 2201.03545
```

### Batch Processing (50 concurrent workers)
```bash
modal run modal/parse_modal.py \
  --batch arxiv_ids.txt \
  --max-workers 50
```

### Skip Database Insertion (Testing Only)
```bash
modal run modal/parse_modal.py \
  --batch test_ids.txt \
  --skip-addition
```

### Skip Evaluation Results (Add Only Datasets)
```bash
modal run modal/parse_modal.py \
  --batch arxiv_ids.txt \
  --skip-step-6
```

## Monitoring

### View Logs in Real-Time

Modal streams logs to your terminal automatically. You can also view them in the Modal dashboard:

1. Go to [modal.com](https://modal.com)
2. Click on "Apps" → "paperswithcode-extraction"
3. View recent runs and logs

### Check Costs

View costs in the Modal dashboard under "Usage".

Approximate costs:
- **Compute**: ~$0.0002/second for 4GB RAM
- **Average paper**: 30 seconds = $0.006
- **Network**: Negligible for database operations
- **Total per paper**: ~$0.10-0.15

For 1,000 papers: ~$100-150

## Performance Tuning

### Adjust Parallelism

```bash
# Conservative (lower cost, slower)
modal run extract_evaluation_results/parse_modal.py --batch ids.txt --max-workers 10

# Aggressive (higher cost, faster)
modal run extract_evaluation_results/parse_modal.py --batch ids.txt --max-workers 100
```

### Adjust Resources

Edit `parse_modal.py`:

```python
@app.function(
    cpu=4.0,      # More CPU for faster processing
    memory=8192,  # More memory for large PDFs
    timeout=1800, # 30 minutes for complex papers
)
```

### Database Connection Pooling

For large batches (1000+ papers), add PgBouncer on your VPS:

```bash
sudo apt install pgbouncer
```

Configure it to pool connections, then point Modal workers to PgBouncer (port 6432) instead of PostgreSQL directly.

## Troubleshooting

### Error: "Secret not found"

Create the secret in Modal dashboard or CLI:
```bash
modal secret create paperswithcode-db PWC_DB_USER=... PWC_DB_PASSWORD=...
```

### Error: "Could not connect to database"

1. Check PostgreSQL is listening on all interfaces:
   ```bash
   sudo netstat -plnt | grep 5432
   ```

2. Check firewall allows connections:
   ```bash
   sudo ufw status | grep 5432
   ```

3. Test connection from your local machine:
   ```bash
   psql -h 167.235.148.241 -U paperswithcode_user -d paperswithcode_hf
   ```

### Error: "Function timed out"

Increase timeout in `parse_modal.py`:
```python
@app.function(
    timeout=1800,  # 30 minutes
)
```

### Error: "Out of memory"

Increase memory allocation:
```python
@app.function(
    memory=8192,  # 8GB
)
```

### Error: "Module not found"

Ensure all dependencies are in the Modal image:
```python
image = (
    modal.Image.debian_slim()
    .pip_install("your-missing-package")
    # ...
)
```

## Scaling to Thousands of Papers

### Step 1: Test with Small Batch (10 papers)
```bash
modal run modal/parse_modal.py \
  --batch small_batch.txt \
  --max-workers 5
```

### Step 2: Scale to Medium Batch (100 papers)
```bash
modal run modal/parse_modal.py \
  --batch medium_batch.txt \
  --max-workers 20
```

### Step 3: Full Scale (1000+ papers)
```bash
modal run modal/parse_modal.py \
  --batch full_batch.txt \
  --max-workers 50
```

**Timeline estimates:**
- 10 papers: ~5 minutes
- 100 papers: ~15 minutes
- 1,000 papers: ~1-2 hours
- 10,000 papers: ~10-20 hours

## Cost Optimization Tips

1. **Use resume=True**: Skip already processed papers
2. **Start with skip-addition**: Test extraction without DB writes
3. **Batch processing**: Process 100-500 papers at a time
4. **Monitor costs**: Check Modal dashboard frequently
5. **Set budgets**: Modal allows setting spending limits

## Alternative: Using GNU Parallel (Local)

For smaller batches or if you want to use your VPS:

```bash
# Process 2 papers at a time locally on your VPS
cat arxiv_ids.txt | parallel -j 2 \
  "uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id {} --resume"
```

This is free but much slower (days vs hours for thousands of papers).

## Next Steps

1. ✓ Set up Modal account
2. ✓ Configure database access
3. ✓ Test single paper
4. □ Process small batch (10-50 papers)
5. □ Monitor costs and performance
6. □ Scale to full dataset

## Support

- Modal Docs: [modal.com/docs](https://modal.com/docs)
- Modal Slack: [modal.com/slack](https://modal.com/slack)
- Issues: File an issue in your repository
