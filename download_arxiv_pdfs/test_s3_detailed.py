#!/usr/bin/env python3
import boto3
from botocore.exceptions import ClientError
import requests

print("🔍 Detailed S3 Access Test")
print("=" * 40)

# Test 1: Basic AWS connectivity
print("\n1. Testing AWS credentials...")
try:
    sts = boto3.client("sts")
    identity = sts.get_caller_identity()
    print("✅ AWS credentials valid")
    print(f"   Account: {identity['Account']}")
    print(f"   User: {identity['Arn']}")
except Exception as e:
    print(f"❌ AWS credentials failed: {e}")
    exit(1)

# Test 2: S3 client creation
print("\n2. Testing S3 client...")
try:
    s3 = boto3.client("s3", region_name="us-east-1")
    print("✅ S3 client created successfully")
except Exception as e:
    print(f"❌ S3 client creation failed: {e}")
    exit(1)

# Test 3: Try different S3 operations
print("\n3. Testing ArXiv bucket access...")

# Test 3a: List bucket (this might fail but gives us info)
try:
    response = s3.list_objects_v2(Bucket="arxiv", Prefix="pdf/", MaxKeys=1)
    print("✅ List objects without RequestPayer worked!")
except ClientError as e:
    print(f"❌ List without RequestPayer failed: {e.response['Error']['Code']}")

# Test 3b: List bucket with RequestPayer
try:
    response = s3.list_objects_v2(
        Bucket="arxiv", Prefix="pdf/", MaxKeys=1, RequestPayer="Requester"
    )
    print("✅ List objects with RequestPayer worked!")
except ClientError as e:
    print(f"❌ List with RequestPayer failed: {e.response['Error']['Code']}")

# Test 3c: Try to access manifest directly
print("\n4. Testing manifest access...")
manifest_key = "pdf/arXiv_pdf_manifest.xml"

try:
    response = s3.get_object(Bucket="arxiv", Key=manifest_key, RequestPayer="Requester")
    print("✅ Manifest download successful!")
    print(f"   Size: {len(response['Body'].read())} bytes")
except ClientError as e:
    error_code = e.response["Error"]["Code"]
    print(f"❌ Manifest download failed: {error_code}")
    print(f"   Error: {e.response['Error']['Message']}")

# Test 4: Alternative - try HTTP access
print("\n5. Testing HTTP access to ArXiv...")
try:
    url = "https://arxiv.org/pdf/arXiv_pdf_manifest.xml"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        print("✅ HTTP access to ArXiv works")
        print(f"   Manifest size via HTTP: {len(response.content)} bytes")
    else:
        print(f"❌ HTTP access failed: {response.status_code}")
except Exception as e:
    print(f"❌ HTTP access error: {e}")

print("\n" + "=" * 40)
print("🎯 Recommendations:")
print("1. If AWS credentials are valid but S3 fails:")
print("   - Check IAM policy includes s3:GetObject for arn:aws:s3:::arxiv/*")
print("   - Wait 5-10 minutes for permissions to propagate")
print("2. If HTTP access works, we can use hybrid approach")
print(
    "3. Consider using AWS CLI to test: aws s3 ls s3://arxiv/pdf/ --request-payer requester"
)
