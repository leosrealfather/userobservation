# AWS Amplify Deployment Guide

This guide explains how to deploy the ProjectManager Usage Dashboard to AWS Amplify with secure credential management.

## Prerequisites

- AWS account with Amplify access
- GitHub repository with your code
- Langfuse API credentials

## Step 1: Prepare Your Repository

1. **Verify `.gitignore` includes sensitive files:**
   - `.streamlit/secrets.toml` ✅ (already ignored)
   - `.env` ✅ (already ignored)

2. **Commit and push your code:**
   ```bash
   git add .
   git commit -m "Add Streamlit dashboard"
   git push origin main
   ```

## Step 2: Create Amplify App

1. Go to [AWS Amplify Console](https://console.aws.amazon.com/amplify/)
2. Click **"New app"** → **"Host web app"**
3. Connect your GitHub repository
4. Select the branch (usually `main` or `master`)

## Step 3: Configure Build Settings

AWS Amplify will auto-detect the Dockerfile. If it doesn't, use these build settings:

**Build specification:**
- Build image: Use default (or select a Python-compatible image)
- Build commands: (Leave empty - Dockerfile handles everything)

Or create `amplify.yml` in your repo root:

```yaml
version: 1
frontend:
  phases:
    build:
      commands:
        - docker build -t streamlit-app .
        - docker run -d -p 8501:8501 streamlit-app
```

**Actually, for Streamlit on Amplify, you'll want to use the Dockerfile directly.**

## Step 4: Set Environment Variables (IMPORTANT - SECURE METHOD)

**This is the secure way to handle credentials in production:**

1. In Amplify Console, go to your app
2. Click **"Environment variables"** in the left sidebar
3. Click **"Manage variables"**
4. Add these three environment variables:

   | Variable Name | Value |
   |--------------|-------|
   | `LANGFUSE_PUBLIC_KEY` | `pk-lf-50be1409-472b-4f83-844f-07816f3cc521` |
   | `LANGFUSE_SECRET_KEY` | `sk-lf-2767ada8-06a5-4b95-9ad4-b5aaaca51504` |
   | `LANGFUSE_BASE_URL` | `https://us.cloud.langfuse.com` |

5. **Mark them as "Secure"** (lock icon) - this encrypts them at rest
6. Click **"Save"**

## Step 5: Configure App Settings

1. Go to **"App settings"** → **"General"**
2. Set **"Port"** to `8501` (Streamlit default)
3. Set **"Health check path"** to `/_stcore/health`

## Step 6: Update Dockerfile for Amplify

The Dockerfile should work, but Amplify might need some adjustments. Verify it includes:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

## Step 7: Deploy

1. Click **"Save and deploy"**
2. Amplify will:
   - Build your Docker image
   - Set up the environment
   - Deploy your app
3. Monitor the build logs for any errors

## Step 8: Verify Deployment

1. Once deployed, click on your app URL
2. The dashboard should load and connect to Langfuse
3. If you see credential errors, double-check the environment variables

## Troubleshooting

### Issue: "Langfuse credentials not found"
- **Solution**: Verify environment variables are set correctly in Amplify console
- Check variable names match exactly: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`

### Issue: Build fails
- **Solution**: Check build logs in Amplify console
- Ensure Dockerfile is in the root directory
- Verify all dependencies are in `requirements.txt`

### Issue: App won't start
- **Solution**: 
  - Check that port 8501 is configured
  - Verify health check path is `/_stcore/health`
  - Check application logs in Amplify console

### Issue: Can't connect to Langfuse
- **Solution**:
  - Verify `LANGFUSE_BASE_URL` is correct (`https://us.cloud.langfuse.com`)
  - Check that API keys are valid
  - Ensure Amplify has internet access (it should by default)

## Security Best Practices

✅ **DO:**
- Use environment variables in Amplify (not files)
- Mark variables as "Secure" in Amplify
- Never commit secrets to git
- Rotate API keys periodically

❌ **DON'T:**
- Commit `secrets.toml` or `.env` files
- Hardcode credentials in code
- Share API keys in chat/email
- Use the same keys for dev and production

## Alternative: Using Amplify's Secret Manager

For even more security, you can use AWS Secrets Manager:

1. Store credentials in AWS Secrets Manager
2. Grant Amplify access to the secret
3. Reference the secret in environment variables

This is more complex but provides additional security layers.

## Cost Considerations

- AWS Amplify hosting: Free tier available, then pay-as-you-go
- Data transfer: Usually minimal for internal dashboards
- Build minutes: Free tier includes build minutes

## Next Steps

After deployment:
1. Set up custom domain (optional)
2. Configure auto-deploy from your git branch
3. Set up monitoring/alerts
4. Document the production URL for your team

