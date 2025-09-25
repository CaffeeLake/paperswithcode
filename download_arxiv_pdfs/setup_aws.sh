#!/bin/bash
# AWS Setup Script for ArXiv PDF Downloads

echo "🔧 AWS Credentials Setup"
echo "========================"
echo ""
echo "You need to get your AWS credentials from the AWS Console:"
echo "1. Go to: https://console.aws.amazon.com/iam/home#/users"
echo "2. Click your username → Security credentials"
echo "3. Create access key → Command Line Interface (CLI)"
echo "4. Copy the Access Key ID and Secret Access Key"
echo ""

# Check if credentials are already set
if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "✅ AWS credentials already set in environment"
    echo "Access Key ID: ${AWS_ACCESS_KEY_ID:0:10}..."
else
    echo "❌ No AWS credentials found in environment"
    echo ""
    echo "To set credentials, run:"
    echo "export AWS_ACCESS_KEY_ID='your-access-key-id'"
    echo "export AWS_SECRET_ACCESS_KEY='your-secret-access-key'"
    echo "export AWS_DEFAULT_REGION='us-east-1'"
    echo ""
    echo "Or create ~/.aws/credentials file:"
    echo "[default]"
    echo "aws_access_key_id = your-access-key-id"
    echo "aws_secret_access_key = your-secret-access-key"
    echo "region = us-east-1"
fi

echo ""
echo "📋 Next Steps:"
echo "1. Set your AWS credentials (above)"
echo "2. Test connection: uv run arxiv_pdfs/s3_bulk_downloader.py --estimate-only"
echo "3. Download PDFs: uv run arxiv_pdfs/s3_bulk_downloader.py --max-files 1"
