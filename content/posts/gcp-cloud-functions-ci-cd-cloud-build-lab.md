---
title: "GCP Lab: Building Serverless Cloud Functions with Cloud Build and IAM Best Practices"
date: "2026-11-25"
draft: false
tags: ["GCP", "Beginner", "Hands-On Lab"]
categories: ["GCP"]
---

## 1. Lab Objective & Free Open-Source Prerequisites

| Goal | Description |
|------|-------------|
| **Deploy a production‑ready Cloud Function** | Use **Cloud Build** to CI/CD a Node.js (or Python) function that responds to HTTP requests. |
| **Implement least‑privilege IAM** | Create custom roles, service accounts, and workload‑identity federation to isolate build, runtime, and monitoring permissions. |
| **Enable observability** | Wire Cloud Logging, Cloud Monitoring, and Error Reporting without additional cost. |
| **Validate end‑to‑end** | Run functional tests, verify logs, and simulate a security breach scenario. |

### Why this Lab is “Free” and “Open‑Source”

| Component | Free Tier Availability | Open‑Source Alternative |
|-----------|-----------------------|--------------------------|
| **gcloud CLI** | Free, cross‑platform binary. | N/A (official Google tool). |
| **Cloud Build** | 120 build‑minutes / month free. | GitHub Actions (if you prefer self‑hosted runners). |
| **Cloud Functions** | 2 M invocations / month free. | Apache OpenWhisk (self‑hosted) – not used here. |
| **Artifact Registry** | 0.5 GiB storage free. | Docker Hub (public) – optional. |
| **IAM** | No extra cost. | Open Policy Agent (OPA) – for policy testing only. |

> **Prerequisite Checklist**  
> 1. A **Google Cloud Platform** (GCP) project with billing enabled.  
> 2. **gcloud** SDK installed locally (v. 470+).  
> 3. **Git** client (any version).  
> 4. A **GitHub** (or GitLab) account for source control.  
> 5. Basic knowledge of **Node.js** (or Python) and **YAML**.  

> **Tip:** All commands below are idempotent where possible; re‑running them will not break the lab.

---

## 2. Enterprise Architecture Topology

The diagram below illustrates the logical flow from **developer commit → Cloud Build → Artifact Registry → Cloud Function → Cloud Logging/Monitoring**. Service accounts are isolated per stage, and a custom IAM role enforces the principle of least privilege.

![Enterprise Architecture Topology](/images/gcp-cloud-functions-cicd-topology.svg)

**Key Points**

* **Developer Workstation** authenticates with a **personal user account** – no service account keys are stored locally.  
* **Cloud Build** runs in a **private VPC** (optional) and uses a **dedicated service account** (`cloudbuild-sa`) that only has `roles/artifactregistry.writer` and `roles/cloudfunctions.developer`.  
* **Cloud Function** runs under its own **runtime service account** (`function-sa`) limited to `roles/logging.logWriter` and `roles/monitoring.metricWriter`.  
* **Custom IAM Role** (`custom.cloudfunctions.builder`) bundles the exact permissions needed for the build pipeline, avoiding the broad `Editor` role.  

---

## 3. Addressing & Resource Inventory Table

| Resource Type | Name (example) | Region | CIDR / Identifier | Purpose |
|---------------|----------------|--------|-------------------|---------|
| **VPC** | `lab-vpc` | `us-central1` | `10.10.0.0/16` | Isolate Cloud Build private workers (optional). |
| **Subnet** | `lab-subnet` | `us-central1-a` | `10.10.10.0/24` | Host Cloud Build private workers. |
| **Service Account (Build)** | `cloudbuild-sa@${PROJECT_ID}.iam.gserviceaccount.com` | N/A | N/A | Executes Cloud Build steps. |
| **Service Account (Function)** | `function-sa@${PROJECT_ID}.iam.gserviceaccount.com` | N/A | N/A | Runtime identity for Cloud Function. |
| **Artifact Registry** | `us-central1-docker.pkg.dev/${PROJECT_ID}/lab-repo` | `us-central1` | N/A | Stores container image for Cloud Function. |
| **Cloud Function** | `hello-world-fn` | `us-central1` | N/A | HTTP endpoint that returns a greeting. |
| **Custom IAM Role** | `custom.cloudfunctions.builder` | N/A | N/A | Least‑privilege permissions for build pipeline. |
| **Cloud Build Trigger** | `repo‑push‑trigger` | N/A | N/A | Fires on push to `main` branch. |
| **Logging Sink** | `function‑logs‑sink` | N/A | N/A | Routes logs to a separate Log Bucket (optional). |

> **Note:** Replace `${PROJECT_ID}` with your actual GCP project identifier throughout the lab.

---

## 4. Step‑by‑Step Configuration

> All commands assume you are logged in with `gcloud auth login` and have set the correct project: `gcloud config set project $PROJECT_ID`.

### 4.1 Create the VPC (optional but recommended for private Cloud Build)

```bash
# Create a custom‑mode VPC
gcloud compute networks create lab-vpc \
    --subnet-mode=custom \
    --bgp-routing-mode=regional \
    --description="VPC for isolated Cloud Build workers" \
    # No external IPs by default

# Create a subnet for Cloud Build private workers
gcloud compute networks subnets create lab-subnet \
    --network=lab-vpc \
    --region=us-central1 \
    --range=10.10.10.0/24 \
    --enable-private-ip-google-access \
    # Allows workers to reach Google APIs without public IPs
```

### 4.2 Create Service Accounts

```bash
# Build service account
gcloud iam service-accounts create cloudbuild-sa \
    --display-name="Cloud Build Service Account"

# Function runtime service account
gcloud iam service-accounts create function-sa \
    --display-name="Cloud Function Runtime Service Account"
```

### 4.3 Define a Custom IAM Role

Create a YAML file `custom-role.yaml`:

```yaml
title: "Cloud Functions Builder"
description: "Least‑privilege role for building and deploying Cloud Functions"
stage: GA
includedPermissions:
  - cloudfunctions.functions.create
  - cloudfunctions.functions.update
  - cloudfunctions.functions.get
  - cloudfunctions.functions.delete
  - artifactregistry.repositories.uploadArtifacts
  - artifactregistry.repositories.get
  - storage.objects.create
  - storage.objects.get
  - logging.logEntries.create
  - monitoring.timeSeries.create
```

Apply the role:

```bash
gcloud iam roles create custom.cloudfunctions.builder \
    --project=$PROJECT_ID \
    --file=custom-role.yaml
```

### 4.4 Bind the Role to Service Accounts

```bash
# Grant the custom role to the Cloud Build SA
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:cloudbuild-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="projects/$PROJECT_ID/roles/custom.cloudfunctions.builder"

# Grant the custom role to the Function SA (only logging & monitoring)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:function-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="projects/$PROJECT_ID/roles/custom.cloudfunctions.builder"
```

### 4.5 Enable Required APIs

```bash
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com \
    iam.googleapis.com
```

### 4.6 Create an Artifact Registry Repository

```bash
gcloud artifacts repositories create lab-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Docker repo for Cloud Function images" \
    --visibility=private
```

### 4.7 Prepare the Function Source Code

Create a local directory `hello-world-fn` and add the following files.

**`package.json`**

```json
{
  "name": "hello-world-fn",
  "version": "1.0.0",
  "main": "index.js",
  "scripts": {
    "start": "node index.js"
  },
  "dependencies": {}
}
```

**`index.js`**

```javascript
/**
 * HTTP Cloud Function that returns a greeting.
 * @param {object} req Express request object.
 * @param {object} res Express response object.
 */
exports.helloWorld = (req, res) => {
  const name = req.query.name || 'World';
  console.log(`Received request for name=${name}`);
  res.status(200).send(`👋 Hello, ${name}!`);
};
```

**`.gcloudignore`** (optional but recommended)

```
node_modules/
.git/
.gitignore
Dockerfile
```

### 4.8 Create a Dockerfile for the Function (Container‑Based Deployment)

```Dockerfile
# Use the official Node.js 20 runtime (slim)
FROM node:20-slim

# Create app directory
WORKDIR /usr/src/app

# Copy package.json and install (no dev deps)
COPY package.json ./
RUN npm ci --only=production

# Copy source code
COPY index.js ./

# Expose the port Cloud Functions expects
EXPOSE 8080

# Run the function using the Functions Framework
RUN npm install -g @google-cloud/functions-framework
CMD ["functions-framework", "--target=helloWorld", "--port=8080"]
```

### 4.9 Push Source to GitHub

```bash
# Initialize git repo (if not already)
git init
git remote add origin https://github.com/<YOUR_GITHUB_USER>/hello-world-fn.git

# Add files and push
git add .
git commit -m "Initial commit – hello world function"
git push -u origin main
```

> **Important:** Ensure the repository is **public** or that you have granted the Cloud Build service account read access via a **GitHub App** or **OAuth token** stored as a secret.

### 4.10 Create a Cloud Build Trigger

```bash
gcloud beta builds triggers create github \
    --name="repo-push-trigger" \
    --repo-owner="<YOUR_GITHUB_USER>" \
    --repo-name="hello-world-fn" \
    --branch-pattern="^main$" \
    --build-config="cloudbuild.yaml" \
    --service-account="cloudbuild-sa@$PROJECT_ID.iam.gserviceaccount.com"
```

### 4.11 Write the Cloud Build Configuration (`cloudbuild.yaml`)

```yaml
steps:
  # 1️⃣ Build the container image
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'us-central1-docker.pkg.dev/${PROJECT_ID}/lab-repo/hello-world-fn:${SHORT_SHA}'
      - '.'
    id: 'Build Image'

  # 2️⃣ Push the image to Artifact Registry
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'us-central1-docker.pkg.dev/${PROJECT_ID}/lab-repo/hello-world-fn:${SHORT_SHA}'
    id: 'Push Image'

  # 3️⃣ Deploy (or update) the Cloud Function
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        gcloud functions deploy hello-world-fn \
          --region=us-central1 \
          --runtime=custom \
          --trigger-http \
          --allow-unauthenticated \
          --entry-point=helloWorld \
          --source=us-central1-docker.pkg.dev/${PROJECT_ID}/lab-repo/hello-world-fn:${SHORT_SHA} \
          --service-account=function-sa@${PROJECT_ID}.iam.gserviceaccount.com \
          --quiet
    id: 'Deploy Function'

images:
  - 'us-central1-docker.pkg.dev/${PROJECT_ID}/lab-repo/hello-world-fn:${SHORT_SHA}'
```

> **Explanation of each step**  
> * **Build Image** – Compiles the Dockerfile into a container image.  
> * **Push Image** – Stores the image in a private Artifact Registry repository.  
> * **Deploy Function** – Uses `gcloud functions deploy` with `--runtime=custom` to point to the container image. The function is bound to `function-sa` for runtime permissions.  

### 4.12 Trigger the First Build Manually (optional)

```bash
gcloud builds submit \
    --config=cloudbuild.yaml \
    --substitutions=_PROJECT_ID=$PROJECT_ID \
    .
```

You should see a streaming log that ends with `SUCCESS`.

### 4.13 Expose the Function URL as a Secret (optional)

```bash
FUNC_URL=$(gcloud functions describe hello-world-fn \
    --region=us-central1 \
    --format='value(httpsTrigger.url)')

echo "Function URL: $FUNC_URL"
```

Store the URL in Secret Manager for downstream services:

```bash
gcloud secrets create hello-world-fn-url \
    --replication-policy="automatic"

echo -n "$FUNC_URL" | gcloud secrets versions add hello-world-fn-url \
    --data-file=-
```

---

## 5. Verification & Troubleshooting Commands

### 5.1 Verify Service Account Permissions

```bash
gcloud iam service-accounts get-iam-policy cloudbuild-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --format=json | jq '.bindings[] | select(.role=="projects/'$PROJECT_ID'/roles/custom.cloudfunctions.builder")'
```

**Expected output (sample)**

```json
{
  "role": "projects/awesome-lab-123/roles/custom.cloudfunctions.builder",
  "members": [
    "serviceAccount:cloudbuild-sa@awesome-lab-123.iam.gserviceaccount.com"
  ]
}
```

If the binding is missing, re‑run the `add-iam-policy-binding` command.

### 5.2 Confirm Artifact Registry Image Exists

```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/$PROJECT_ID/lab-repo \
    --include-tags
```

**Expected output (sample)**

```
NAME                                          TAGS
us-central1-docker.pkg.dev/awesome-lab-123/lab-repo/hello-world-fn   latest, 1a2b3c4d
```

### 5.3 Test the Deployed Cloud Function

```bash
curl -s "$(gcloud functions describe hello-world-fn \
    --region=us-central1 \
    --format='value(httpsTrigger.url)')" \
    -d '' \
    -w "\nHTTP %{http_code}\n"
```

**Expected output**

```
👋 Hello, World!
HTTP 200
```

Add a query string to verify parameter handling:

```bash
curl -s "$(gcloud functions describe hello-world-fn \
    --region=us-central1 \
    --format='value(httpsTrigger.url)')?name=GCP+Wizard"
```

**Expected output**

```
👋 Hello, GCP Wizard!
```

### 5.4 Check Cloud Logging for the Request

```bash
gcloud logging read "resource.type=\"cloud_function\" AND resource.labels.function_name=\"hello-world-fn\" AND severity>=INFO" \
    --limit=5 \
    --format="value(textPayload)"
```

**Sample output**

```
Received request for name=World
Received request for name=GCP Wizard
```

If no logs appear, verify that the **function‑sa** has `roles/logging.logWriter` (it should via the custom role).

### 5.5 Common Failure Scenarios & Fixes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| **Build fails at “Push Image”** | Artifact Registry repository does not exist or IAM denies `artifactregistry.repositories.uploadArtifacts`. | Re‑run the repository creation command and ensure the custom role includes `artifactregistry.repositories.uploadArtifacts`. |
| **Deploy step times out** | Cloud Build worker cannot reach `cloudfunctions.googleapis.com` (private VPC without Private Google Access). | Add `--enable-private-ip-google-access` to the subnet or remove the VPC isolation for the build. |
| **Function returns 403** | `function-sa` missing `roles/cloudfunctions.invoker` for unauthenticated calls. | Grant `roles/cloudfunctions.invoker` to `allUsers` (if public) or to a specific identity. |
| **Logs missing** | `function-sa` lacks `roles/logging.logWriter`. | Add the permission via the custom role or directly bind `roles/logging.logWriter`. |
| **Build trigger not firing** | GitHub webhook not configured or secret token mismatch. | Re‑create the trigger with the correct GitHub App installation or use a personal access token stored as a secret. |

---

## 6. Security Hardening & Production Best Practices

### 6.1 Principle of Least Privilege (PoLP)

| Entity | Permissions Granted | Rationale |
|--------|---------------------|-----------|
| **cloudbuild-sa** | `custom.cloudfunctions.builder` (contains only build & deploy actions) | Prevents accidental deletion of unrelated resources. |
| **function-sa** | `roles/logging.logWriter`, `roles/monitoring.metricWriter`, `roles/cloudfunctions.invoker` (if internal) | Limits runtime to observability and inbound request handling only. |
| **GitHub Actions (optional)** | `roles/cloudbuild.builds.editor` (read‑only) | Allows CI pipelines to trigger builds without full admin rights. |

### 6.2 Use **Workload Identity Federation** for CI/CD

Instead of storing long‑lived service‑account keys, configure **Workload Identity Federation** so that GitHub Actions can impersonate `cloudbuild-sa` using OIDC tokens.

```bash
# 1️⃣ Create a workload identity pool
gcloud iam workload-identity-pools create github-pool \
    --location="global" \
    --description="Pool for GitHub OIDC" \
    --display-name="GitHub Pool"

# 2️⃣ Create a provider inside the pool
gcloud iam workload-identity-pools providers create-oidc github-provider \
    --workload-identity-pool=github-pool \
    --location="global" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"

# 3️⃣ Allow the provider to impersonate the Cloud Build SA
gcloud iam service-accounts add-iam-policy-binding cloudbuild-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/<YOUR_GITHUB_USER>/hello-world-fn" \
    --role="roles/iam.workloadIdentityUser"
```

In your GitHub workflow, add:

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - name: Authenticate to GCP
    id: auth
    uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: "projects/${{ env.PROJECT_NUMBER }}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
      service_account: "cloudbuild-sa@${{ env.PROJECT_ID }}.iam.gserviceaccount.com"
```

### 6.3 Enable **Binary Authorization** for Container Images

```bash
gcloud binary-authorization policies create \
    --project=$PROJECT_ID \
    --admission-whitelist-patterns=".*" \
    --default-action=deny
```

*Only images signed with a trusted key can be deployed.*  
Create a **Key Management Service (KMS)** key, sign the image, and add the attestor to the policy.

### 6.4 Enforce **VPC‑Connector** for Outbound Traffic

If your function needs to call internal services (e.g., Cloud SQL), attach a VPC connector:

```bash
gcloud compute networks vpc-access connectors create function-connector \
    --region=us-central1 \
    --network=lab-vpc \
    --range=10.8.0.0/28

gcloud functions deploy hello-world-fn \
    --region=us-central1 \
    --runtime=custom \
    --trigger-http \
    --vpc-connector=function-connector \
    --vpc-connector-egress-settings=private-ranges-only
```

### 6.5 Set **Maximum Instance Count** to Prevent Cost Surprises

```bash
gcloud functions deploy hello-world-fn \
    --region=us-central1 \
    --runtime=custom \
    --trigger-http \
    --max-instances=10 \
    --quiet
```

*Limits the function to 10 concurrent instances, capping compute cost.*

### 6.6 Enable **Cloud Audit Logging** for IAM Changes

```bash
gcloud logging sinks create iam-audit-sink \
    "storage.googleapis.com/${PROJECT_ID}_audit_logs" \
    --log-filter='resource.type="iam_role" OR protoPayload.serviceName="iam.googleapis.com"' \
    --include-children
```

*All IAM role creations, deletions, and bindings are archived for forensic analysis.*

### 6.7 Rotate Secrets Regularly

If you store the function URL or other credentials in Secret Manager, schedule a Cloud Scheduler job that:

1. Generates a new secret version.  
2. Updates any downstream services via Pub/Sub.  

Example Cloud Scheduler command:

```bash
gcloud scheduler jobs create http rotate-fn-url \
    --schedule="0 0 * * 0" \
    --uri="https://cloudfunctions.googleapis.com/v1/projects/$PROJECT_ID/locations/us-central1/functions/hello-world-fn" \
    --http-method=POST \
    --oauth-service-account-email=function-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --message-body='{"updateMask":"httpsTrigger.url"}'
```

### 6.8 Monitoring & Alerting

Create an alert policy that fires when **error count > 5** in a 5‑minute window:

```bash
gcloud monitoring alert-policies create \
    --display-name="Cloud Function Error Spike" \
    --conditions='{
        "displayName":"Error Rate",
        "conditionThreshold":{
            "filter":"resource.type=\"cloud_function\" AND metric.type=\"cloudfunctions.googleapis.com/function/execution_count\" AND metric.label."status"=\"error\"",
            "comparison":"COMPARISON_GT",
            "thresholdValue":5,
            "duration":"300s",
            "trigger":{
                "count":1
            }
        }
    }' \
    --notification-channels=$(gcloud monitoring channels list --format='value(name)')
```

### 6.9 Documentation & Change Management

* Store the **cloudbuild.yaml**, **Dockerfile**, and **IAM role definition** in a version‑controlled repository.  
* Tag each release with a semantic version (`v1.0.0`, `v1.1.0`).  
* Use **GitHub Pull Requests** with mandatory code‑review approvals before merging to `main`.  

---

### 🎉 Lab Completion Checklist

- [ ] VPC and subnet created (optional).  
- [ ] Service accounts (`cloudbuild-sa`, `function-sa`) provisioned.  
- [ ] Custom IAM role defined and bound.  
- [ ] Artifact Registry repository ready.  
- [ ] Source code committed to GitHub.  
- [ ] Cloud Build trigger configured.  
- [ ] `cloudbuild.yaml` validated and first build succeeded.  
- [ ] Cloud Function reachable via HTTPS and returns expected greeting.  
- [ ] Logs appear in Cloud Logging; metrics in Cloud Monitoring.  
- [ ] Security hardening steps (Workload Identity, Binary Authorization, VPC‑Connector, Max Instances) applied.  

You now have a **production‑grade, serverless pipeline** that demonstrates modern GCP DevSecOps practices. Feel free to extend the lab by adding a Pub/Sub trigger, integrating Cloud Run for background processing, or experimenting with **Terraform** to codify the entire infrastructure. Happy building!