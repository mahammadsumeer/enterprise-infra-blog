---
title: "AWS Lab: Deploying a Secure Static Website on S3 with CloudFront and WAF"
date: "2026-11-23"
draft: false
tags: ["AWS Solutions Architect", "Beginner", "Hands-On Lab"]
categories: ["AWS Solutions Architect"]
---

## 1. Lab Objective & Free Open-Source Prerequisites

### 1.1 Lab Objective
The purpose of this hands‑on lab is to guide you through the end‑to‑end deployment of a **production‑grade static website** that is:

* **Hosted on Amazon S3** (object storage) with static‑website hosting enabled.
* **Delivered globally via Amazon CloudFront** (CDN) with an **ACM‑managed TLS certificate**.
* **Protected by AWS WAF** (Web Application Firewall) using a managed rule‑group and a custom IP‑allowlist.
* **Exposed through a custom domain** managed in Amazon Route 53.
* **Monitored and hardened** with logging, versioning, bucket policies, and least‑privilege IAM.

By the end of the lab you will have a reproducible IaC‑style workflow (using AWS CLI and CloudFormation) that can be promoted from a sandbox environment to production with minimal changes.

### 1.2 Free / Open‑Source Prerequisites
| Item | Reason | Free Tier / OSS Status |
|------|--------|------------------------|
| **AWS Account** (12‑month Free Tier) | Provides access to S3, CloudFront, WAF, ACM, Route 53 (hosted zones are free for the first 50 records) | Free tier includes 5 GB of S3 Standard storage, 50 GB data transfer out, 2 M CloudFront requests per month |
| **AWS CLI v2** | Command‑line automation for all services | Open‑source, downloadable from <https://aws.amazon.com/cli/> |
| **jq** (JSON processor) | Parsing CLI JSON output for verification | Open‑source (MIT) |
| **Git** | Version control for IaC templates | Open‑source (GPL) |
| **Visual Studio Code** (or any editor) | Editing Markdown, JSON, YAML, and shell scripts | Open‑source (MIT) |
| **Docker (optional)** | Run a local static site generator (e.g., Hugo) to produce HTML files for upload | Open‑source (Apache 2.0) |
| **cURL / wget** | Simple HTTP client for verification | Open‑source |

> **Note:** All commands below assume you have configured the AWS CLI with `aws configure` and that the default profile has sufficient IAM permissions (see the *Security Hardening* section for the exact policy).

---

## 2. Enterprise Architecture Topology

The following diagram illustrates the logical flow of traffic and the AWS services that compose the solution. It is deliberately kept simple for clarity but reflects a production‑ready pattern.

```mermaid
graph LR
    User["End‑User (Browser)"]
    DNS["Route 53 Hosted Zone"]
    CF["CloudFront Distribution"]
    WAF["AWS WAF (Managed + Custom Rules)"]
    ACM["ACM Certificate (us-east-1)"]
    S3["S3 Bucket (Static Site)"]
    LogS3["S3 Bucket (Access Logs)"]
    CloudWatch["CloudWatch Logs"]
    IAM["IAM Role (S3‑Read‑Only)"]
    GitHub["GitHub Repo (Site Source)"]

    User -->|HTTPS request| DNS
    DNS -->|CNAME| CF
    CF -->|HTTPS (TLS) | ACM
    CF -->|WAF inspection| WAF
    WAF -->|Allowed| CF
    CF -->|GET Object| S3
    S3 -->|Object| CF
    CF -->|Access Log| LogS3
    LogS3 -->|S3 Event| CloudWatch
    IAM -->|Read| S3
    GitHub -->|git clone| S3
```

*All node labels are wrapped in double quotes as required by the Mermaid rule.*

---

## 3. Addressing & Resource Inventory Table

| Resource | Logical Name | AWS Identifier (example) | Region | Purpose |
|----------|--------------|--------------------------|--------|---------|
| S3 bucket for website content | `my-static-site-prod` | `my-static-site-prod` | `us-east-1` | Stores HTML, CSS, JS, images |
| S3 bucket for CloudFront logs | `my-static-site-logs` | `my-static-site-logs` | `us-east-1` | Retains access logs for audit |
| CloudFront distribution | `my-static-site-cf` | `E1A2B3C4D5E6F7` | Global (edge) | CDN front‑end with TLS |
| ACM certificate | `my-static-site-cert` | `arn:aws:acm:us-east-1:123456789012:certificate/abcd-efgh-ijkl` | `us-east-1` | Provides HTTPS for the custom domain |
| Route 53 hosted zone | `example.com` | `Z3P5QSUBK4POTI` | Global | DNS authority for `www.example.com` |
| WAF web ACL | `my-static-site-waf` | `arn:aws:wafv2:us-east-1:123456789012:regional/webacl/my-static-site-waf/abcd1234` | `us-east-1` | Blocks OWASP Top 10 attacks |
| IAM policy (S3 read‑only) | `S3ReadOnlyStaticSite` | `arn:aws:iam::123456789012:policy/S3ReadOnlyStaticSite` | Global | Grants CloudFront origin access |
| IAM role (CloudFront OAI) | `CF-OAI-Role` | `arn:aws:iam::123456789012:role/CF-OAI-Role` | Global | Enables OAI to read from S3 |
| GitHub repository | `github.com/yourorg/static-site` | N/A | N/A | Source of static assets |

---

## 4. Step‑by‑Step Configuration

> **Tip:** Copy each block into a terminal session. Commands are fully idempotent where possible; re‑running them will not create duplicate resources.

### 4.1 Set Global Variables

```bash
# --------------------------------------------------------------
# Global variables – adjust to your own naming conventions
# --------------------------------------------------------------
export AWS_REGION=us-east-1
export DOMAIN=example.com                # Your registered domain
export SUBDOMAIN=www                     # Sub‑domain for the site
export SITE_BUCKET=my-static-site-prod
export LOG_BUCKET=my-static-site-logs
export CF_DISTRIBUTION_ID=               # Will be populated later
export ACM_CERT_ARN=                     # Will be populated later
export WAF_WEBACL_ARN=                   # Will be populated later
```

### 4.2 Create S3 Buckets

```bash
# --------------------------------------------------------------
# 1️⃣ Create the primary bucket for static website content
# --------------------------------------------------------------
aws s3api create-bucket \
    --bucket $SITE_BUCKET \
    --region $AWS_REGION \
    --create-bucket-configuration LocationConstraint=$AWS_REGION \
    --acl private

# Enable static website hosting (index & error documents)
aws s3 website s3://$SITE_BUCKET \
    --index-document index.html \
    --error-document error.html

# Enable versioning (helps rollback)
aws s3api put-bucket-versioning \
    --bucket $SITE_BUCKET \
    --versioning-configuration Status=Enabled

# --------------------------------------------------------------
# 2️⃣ Create a dedicated bucket for CloudFront access logs
# --------------------------------------------------------------
aws s3api create-bucket \
    --bucket $LOG_BUCKET \
    --region $AWS_REGION \
    --create-bucket-configuration LocationConstraint=$AWS_REGION \
    --acl log-delivery-write

# Enforce server‑side encryption (SSE‑S3)
aws s3api put-bucket-encryption \
    --bucket $LOG_BUCKET \
    --server-side-encryption-configuration \
        '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Block public access (logs must stay private)
aws s3api put-public-access-block \
    --bucket $LOG_BUCKET \
    --public-access-block-configuration \
        '{"BlockPublicAcls":true,"IgnorePublicAcls":true,"BlockPublicPolicy":true,"RestrictPublicBuckets":true}'
```

### 4.3 Upload Sample Site Content

You can generate a simple HTML page locally or clone an existing repo. Below we use a minimal index page.

```bash
# --------------------------------------------------------------
# Create a temporary directory and a simple index.html
# --------------------------------------------------------------
mkdir -p /tmp/static-site
cat > /tmp/static-site/index.html <<'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Welcome to My Secure Static Site</title>
    <style>
        body {font-family:Arial,Helvetica,sans-serif; margin:2rem; background:#f4f4f9;}
        h1 {color:#2c3e50;}
    </style>
</head>
<body>
    <h1>Hello, world! 🎉</h1>
    <p>This site is served from Amazon S3, accelerated by CloudFront, and protected by AWS WAF.</p>
</body>
</html>
EOF

# Sync the folder to the S3 bucket (private ACL)
aws s3 sync /tmp/static-site s3://$SITE_BUCKET --acl private
```

### 4.4 Provision an ACM Certificate (us-east-1 is mandatory for CloudFront)

```bash
# --------------------------------------------------------------
# Request a public certificate for www.example.com
# --------------------------------------------------------------
aws acm request-certificate \
    --region us-east-1 \
    --domain-name $SUBDOMAIN.$DOMAIN \
    --validation-method DNS \
    --idempotency-token $(date +%s) \
    --options CertificateTransparencyLoggingPreference=ENABLED \
    --output json > /tmp/acm-request.json

# Extract the ARN for later use
export ACM_CERT_ARN=$(jq -r '.CertificateArn' /tmp/acm-request.json)

# --------------------------------------------------------------
# Retrieve the DNS validation record that ACM expects
# --------------------------------------------------------------
aws acm describe-certificate \
    --certificate-arn $ACM_CERT_ARN \
    --region us-east-1 \
    --query 'Certificate.DomainValidationOptions[0].ResourceRecord' \
    --output json > /tmp/acm-dns.json

# Create the DNS record in Route 53
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones-by-name \
    --dns-name $DOMAIN \
    --query "HostedZones[0].Id" \
    --output text | cut -d'/' -f3)

cat > /tmp/route53-change-batch.json <<'EOF'
{
  "Comment": "ACM DNS validation for CloudFront",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "__NAME__",
        "Type": "__TYPE__",
        "TTL": 300,
        "ResourceRecords": [{ "Value": "__VALUE__" }]
      }
    }
  ]
}
EOF

# Populate placeholders
NAME=$(jq -r '.Name' /tmp/acm-dns.json)
TYPE=$(jq -r '.Type' /tmp/acm-dns.json)
VALUE=$(jq -r '.Value' /tmp/acm-dns.json)

sed -i "s/__NAME__/$NAME/; s/__TYPE__/$TYPE/; s/__VALUE__/$VALUE/" /tmp/route53-change-batch.json

# Submit the change
aws route53 change-resource-record-sets \
    --hosted-zone-id $HOSTED_ZONE_ID \
    --change-batch file:///tmp/route53-change-batch.json

# Wait for validation (max 10 min)
aws acm wait certificate-validated \
    --certificate-arn $ACM_CERT_ARN \
    --region us-east-1
```

### 4.5 Create an Origin Access Identity (OAI) for CloudFront

```bash
# --------------------------------------------------------------
# Create OAI – this will be used to give CloudFront read‑only
# access to the S3 bucket without making the bucket public.
# --------------------------------------------------------------
OAI_ID=$(aws cloudfront create-cloud-front-origin-access-identity \
    --cloud-front-origin-access-identity-config \
        CallerReference=$(date +%s),Comment="OAI for $SITE_BUCKET" \
    --query 'CloudFrontOriginAccessIdentity.Id' \
    --output text)

# Build the canonical user ID for the OAI
OAI_S3_CANONICAL_USER_ID=$(aws cloudfront get-cloud-front-origin-access-identity-config \
    --id $OAI_ID \
    --query 'CloudFrontOriginAccessIdentity.S3CanonicalUserId' \
    --output text)
```

### 4.6 Apply a Bucket Policy to Allow OAI Access

```bash
cat > /tmp/bucket-policy.json <<EOF
{
  "Version":"2012-10-17",
  "Statement":[{
    "Sid":"AllowCloudFrontRead",
    "Effect":"Allow",
    "Principal":{"AWS":"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity $OAI_ID"},
    "Action":"s3:GetObject",
    "Resource":"arn:aws:s3:::$SITE_BUCKET/*"
  }]
}
EOF

aws s3api put-bucket-policy \
    --bucket $SITE_BUCKET \
    --policy file:///tmp/bucket-policy.json
```

### 4.7 Deploy AWS WAF Web ACL

```bash
# --------------------------------------------------------------
# 1️⃣ Create a WAFv2 Web ACL in the global scope (for CloudFront)
# --------------------------------------------------------------
WAF_WEBACL_ARN=$(aws wafv2 create-web-acl \
    --name my-static-site-waf \
    --scope CLOUDFRONT \
    --default-action Block={} \
    --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=myStaticSiteWAF \
    --rules '[
        {
            "Name":"AWSManagedRulesCommonRuleSet",
            "Priority":0,
            "Statement":{"ManagedRuleGroupStatement":{"VendorName":"AWS","Name":"AWSManagedRulesCommonRuleSet"}},
            "OverrideAction":{"None":{}},
            "VisibilityConfig":{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"AWSManagedRulesCommonRuleSet"}
        },
        {
            "Name":"IPAllowlist",
            "Priority":1,
            "Statement":{"IPSetReferenceStatement":{"ARN":"arn:aws:wafv2:us-east-1:123456789012:regional/ipset/AllowedIPs/abcd1234"}},
            "Action":{"Allow":{}},
            "VisibilityConfig":{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"IPAllowlist"}
        }
    ]' \
    --output json \
    --query 'Summary.ARN' \
    --region us-east-1 | tr -d '"')
```

> **Note:** The `IPSetReferenceStatement` assumes you have already created an IP set named `AllowedIPs`. If you do not need a custom IP allowlist, simply omit the second rule.

### 4.8 Create the CloudFront Distribution

```bash
# --------------------------------------------------------------
# Build the CloudFront distribution JSON payload
# --------------------------------------------------------------
cat > /tmp/cloudfront-config.json <<'EOF'
{
  "CallerReference": "__CALLER_REF__",
  "Aliases": {
    "Quantity": 1,
    "Items": ["__FULL_DOMAIN__"]
  },
  "DefaultRootObject": "index.html",
  "Origins": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "S3-StaticSite",
        "DomainName": "__S3_BUCKET_NAME__.s3.amazonaws.com",
        "OriginPath": "",
        "S3OriginConfig": {
          "OriginAccessIdentity": "origin-access-identity/cloudfront/__OAI_ID__"
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "S3-StaticSite",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 2,
      "Items": ["GET","HEAD"],
      "CachedMethods": {
        "Quantity": 2,
        "Items": ["GET","HEAD"]
      }
    },
    "Compress": true,
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",   // Managed-CachingOptimized
    "OriginRequestPolicyId": "88a5eaf4-2fd4-4f17-bc66-7c1a9c8c5c6b", // Managed-AllViewer
    "ResponseHeadersPolicyId": "67f7725c-6f97-4210-82d7-5d9c9b5e2c6f", // Managed-SecurityHeadersPolicy
    "TrustedSigners": {"Enabled": false, "Quantity": 0}
  },
  "CacheBehaviors": {"Quantity": 0},
  "CustomErrorResponses": {"Quantity": 0},
  "Comment": "Production static site for __FULL_DOMAIN__",
  "Logging": {
    "Enabled": true,
    "IncludeCookies": false,
    "Bucket": "__LOG_BUCKET__.s3.amazonaws.com",
    "Prefix": "cloudfront/"
  },
  "PriceClass": "PriceClass_100",
  "Enabled": true,
  "ViewerCertificate": {
    "ACMCertificateArn": "__ACM_CERT_ARN__",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021"
  },
  "WebACLId": "__WAF_WEBACL_ARN__",
  "HttpVersion": "http2",
  "IsIPV6Enabled": true
}
EOF

# Populate placeholders
sed -i "s/__CALLER_REF__/$(date +%s)/" /tmp/cloudfront-config.json
sed -i "s/__FULL_DOMAIN__/$SUBDOMAIN.$DOMAIN/" /tmp/cloudfront-config.json
sed -i "s/__S3_BUCKET_NAME__/$SITE_BUCKET/" /tmp/cloudfront-config.json
sed -i "s/__OAI_ID__/$OAI_ID/" /tmp/cloudfront-config.json
sed -i "s/__LOG_BUCKET__/$LOG_BUCKET/" /tmp/cloudfront-config.json
sed -i "s|__ACM_CERT_ARN__|$ACM_CERT_ARN|" /tmp/cloudfront-config.json
sed -i "s|__WAF_WEBACL_ARN__|$WAF_WEBACL_ARN|" /tmp/cloudfront-config.json

# --------------------------------------------------------------
# Create the distribution
# --------------------------------------------------------------
aws cloudfront create-distribution-with-tags \
    --distribution-config file:///tmp/cloudfront-config.json \
    --tags Items=[{Key=Environment,Value=Production}] \
    --output json > /tmp/cf-create-output.json

# Capture the Distribution ID for later steps
export CF_DISTRIBUTION_ID=$(jq -r '.Distribution.Id' /tmp/cf-create-output.json)

echo "✅ CloudFront Distribution ID: $CF_DISTRIBUTION_ID"
```

### 4.9 Create Route 53 Record Set

```bash
# --------------------------------------------------------------
# Add an A (ALIAS) record that points the sub‑domain to the CloudFront distribution
# --------------------------------------------------------------
cat > /tmp/route53-alias.json <<EOF
{
  "Comment": "Alias for CloudFront distribution",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "$SUBDOMAIN.$DOMAIN.",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "Z2FDTNDATAQYW2",   # CloudFront hosted zone (global)
          "DNSName": "$(jq -r '.Distribution.DomainName' /tmp/cf-create-output.json).",
          "EvaluateTargetHealth": false
        }
      }
    },
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "$SUBDOMAIN.$DOMAIN.",
        "Type": "AAAA",
        "AliasTarget": {
          "HostedZoneId": "Z2FDTNDATAQYW2",
          "DNSName": "$(jq -r '.Distribution.DomainName' /tmp/cf-create-output.json).",
          "EvaluateTargetHealth": false
        }
      }
    }
  ]
}
EOF

aws route53 change-resource-record-sets \
    --hosted-zone-id $HOSTED_ZONE_ID \
    --change-batch file:///tmp/route53-alias.json
```

### 4.10 Enable CloudFront Access Logging (already configured in the distribution JSON) – verify

```bash
aws cloudfront get-distribution-config \
    --id $CF_DISTRIBUTION_ID \
    --output json | jq '.DistributionConfig.Logging'
```

You should see `"Enabled": true` and the `Bucket` set to `$LOG_BUCKET.s3.amazonaws.com`.

### 4.11 (Optional) Deploy via CloudFormation for repeatability

If you prefer IaC, you can store the JSON payloads above in a CloudFormation template (`static-site.yaml`). The template would define:

* `AWS::S3::Bucket` (website bucket, log bucket)
* `AWS::CloudFront::Distribution`
* `AWS::WAFv2::WebACL`
* `AWS::CertificateManager::Certificate`
* `AWS::Route53::RecordSet`

Running the template:

```bash
aws cloudformation deploy \
    --template-file static-site.yaml \
    --stack-name static-site-prod \
    --parameter-overrides \
        DomainName=$SUBDOMAIN.$DOMAIN \
        SiteBucketName=$SITE_BUCKET \
        LogBucketName=$LOG_BUCKET \
    --capabilities CAPABILITY_NAMED_IAM
```

---

## 5. Verification & Troubleshooting Commands

### 5.1 Verify DNS Resolution

```bash
dig +short $SUBDOMAIN.$DOMAIN
```

**Expected output** (example):

```
d111111abcdef8.cloudfront.net.
```

If the answer is the CloudFront domain name, DNS is correctly pointing.

### 5.2 Test HTTPS Access

```bash
curl -I https://$SUBDOMAIN.$DOMAIN
```

**Expected headers** (truncated):

```
HTTP/2 200 
content-type: text/html
content-length: 1234
date: Thu, 23 Nov 2026 12:34:56 GMT
x-amz-cf-id: abcdef1234567890
x-amz-cf-pop: IAD79-C3
strict-transport-security: max-age=31536000; includeSubDomains; preload
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
```

Key points to check:

* **200 OK** – the site is reachable.
* **Strict‑Transport‑Security** header – confirms the security header policy.
* **x-amz-cf-id** – indicates the request passed through CloudFront.

### 5.3 Confirm WAF is Active

```bash
aws wafv2 get-web-acl \
    --arn $WAF_WEBACL_ARN \
    --scope CLOUDFRONT \
    --output json | jq '.WebACL.DefaultAction'
```

**Expected output**:

```json
{
  "Block": {}
}
```

The default action is `Block`, meaning any request not explicitly allowed by a rule will be denied.

### 5.4 Simulate a Blocked Request (SQLi payload)

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
    "https://$SUBDOMAIN.$DOMAIN/?search=%27%20OR%201%3D1--"
```

**Expected output**:

```
403
```

A `403 Forbidden` indicates the AWS Managed Rules detected a potential SQL injection and blocked it.

### 5.5 Check CloudFront Access Logs

```bash
aws s3 ls s3://$LOG_BUCKET/cloudfront/ --recursive | head
```

You should see log objects with names like:

```
2026-11-23-12-00-00-ABCDEFGHIJ1234.gz
```

Download and inspect a recent log:

```bash
aws s3 cp s3://$LOG_BUCKET/cloudfront/2026-11-23-12-00-00-ABCDEFGHIJ1234.gz - | gunzip -c | head
```

Sample line (Common Log Format):

```
2026-11-23	12:00:01	ABCDEFGHIJ1234	192.0.2.44	GET	/www.example.com/index.html	200	-	"https://www.google.com"	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"	-	-	RefreshHit	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-	-