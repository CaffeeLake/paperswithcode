#!/usr/bin/env python3
import boto3
from botocore.exceptions import ClientError

# Test S3 access
s3 = boto3.client("s3")

print("Testing S3 access to ArXiv bucket...")

try:
    # Test 1: Check if we can access the manifest
    response = s3.head_object(
        Bucket="arxiv", Key="pdf/arXiv_pdf_manifest.xml", RequestPayer="Requester"
    )
    print("✅ Manifest access successful!")
    print(f"Manifest size: {response['ContentLength']} bytes")

except ClientError as e:
    error_code = e.response["Error"]["Code"]
    print(f"❌ Manifest access failed: {error_code}")
    print(f"Error: {e}")

    # Try alternative approach
    if error_code == "403":
        print("\n🔧 Trying alternative permissions...")
        try:
            # Test with different approach
            response = s3.get_object(
                Bucket="arxiv",
                Key="pdf/arXiv_pdf_manifest.xml",
                RequestPayer="Requester",
            )
            print("✅ Alternative access method worked!")
        except Exception as e2:
            print(f"❌ Alternative method also failed: {e2}")

print("\n📋 AWS Account Info:")
try:
    sts = boto3.client("sts")
    identity = sts.get_caller_identity()
    print(f"Account ID: {identity['Account']}")
    print(f"User ARN: {identity['Arn']}")
except Exception as e:
    print(f"Could not get identity: {e}")
