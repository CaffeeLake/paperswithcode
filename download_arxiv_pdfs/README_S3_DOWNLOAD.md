# ArXiv S3 Bulk Download Guide

## 🎉 **Much Better Solution!**

Instead of fighting ArXiv's rate limits, we can download PDFs directly from their official S3 bucket. This is:

- ✅ **Official and supported** by ArXiv
- ✅ **No rate limits** or captchas
- ✅ **Much faster** - bulk downloads
- ✅ **Cost-effective** - only pay for what you download
- ✅ **Reliable** - no IP blocking issues

## 📊 **The Numbers**

Based on [ArXiv's S3 documentation](https://info.arxiv.org/help/bulk_data_s3.html):

- **Total ArXiv PDFs**: ~2.7 TB (as of March 2023)
- **Growth rate**: ~100 GB/month
- **Our dataset**: 58,966 papers from HuggingFace
- **Estimated cost**: $5-15 USD (much cheaper than VPS/VPN costs!)

## 🔧 **Setup Instructions**

### 1. Get AWS Credentials

You need an AWS account (free tier is fine):

1. Go to [AWS Console](https://aws.amazon.com/console/)
2. Create account or sign in
3. Go to IAM → Users → Create User
4. Attach policy: `AmazonS3ReadOnlyAccess`
5. Create access keys

### 2. Configure AWS CLI

```bash
# Configure credentials
aws configure

# Enter when prompted:
# AWS Access Key ID: [your-access-key]
# AWS Secret Access Key: [your-secret-key]
# Default region: us-east-1
# Default output format: json
```

### 3. Test Access

```bash
# Get cost estimate (no download)
uv run pdfs/s3_bulk_downloader.py --estimate-only

# Test with small batch
uv run pdfs/s3_bulk_downloader.py --max-files 1
```

### 4. Full Download

```bash
# Download all PDFs for our 58,966 papers
uv run pdfs/s3_bulk_downloader.py \
    --csv data/arxiv_papers_hf.csv \
    --output-dir pdfs/s3_downloaded
```

## 💰 **Cost Breakdown**

ArXiv S3 uses "requester pays" model:

- **Data transfer**: ~$0.09 per GB
- **Our estimate**: 58,966 papers ≈ 50-150 GB ≈ **$5-15 USD**
- **Compare to**: VPN services ($5-10/month), multiple VPS ($50+/month)

## 🚀 **Advantages Over Rate-Limited Approach**

| Aspect | Individual Downloads | S3 Bulk Download |
|--------|---------------------|------------------|
| **Speed** | 2-3 months | 2-6 hours |
| **Cost** | VPN/VPS: $50+ | AWS: $5-15 |
| **Reliability** | Constant blocks | 100% reliable |
| **Complexity** | High (IP rotation) | Low (simple S3) |
| **Official** | Against ToS | Officially supported |

## 📁 **How It Works**

1. **Download manifest**: Lists all PDF tar files with metadata
2. **Filter relevant files**: Only download tars containing our papers
3. **Extract selectively**: Only extract PDFs we need from each tar
4. **Organize output**: Clean directory structure with individual PDFs

## 🔍 **File Structure**

```
pdfs/s3_downloaded/
├── 2302.11211.pdf
├── 2302.11223.pdf
├── 2302.11313.pdf
└── ... (58,966 total PDFs)
```

## ⚡ **Performance Estimates**

- **Download speed**: Limited by your internet (typically 50-500 Mbps)
- **Processing time**: ~1-2 hours for manifest + filtering
- **Total time**: 2-6 hours depending on connection
- **Storage needed**: ~50-150 GB for all PDFs

## 🛠️ **Commands Reference**

```bash
# Setup
uv run pdfs/s3_bulk_downloader.py --setup

# Cost estimate only
uv run pdfs/s3_bulk_downloader.py --estimate-only

# Test with 1 file
uv run pdfs/s3_bulk_downloader.py --max-files 1

# Download first 10 files (testing)
uv run pdfs/s3_bulk_downloader.py --max-files 10

# Full download
uv run pdfs/s3_bulk_downloader.py
```

## 🔒 **Security & Compliance**

- Uses official ArXiv S3 bucket
- Respects ArXiv's terms of service
- Only downloads papers you have legitimate access to
- No circumvention of rate limits (uses official bulk access)

## 🎯 **Next Steps**

1. **Setup AWS credentials** (5 minutes)
2. **Get cost estimate** (1 minute)
3. **Test with small batch** (5 minutes)
4. **Run full download** (2-6 hours)
5. **Integrate with your application** (done!)

This approach is **much better** than the VPN/rate-limiting workarounds we were building!
