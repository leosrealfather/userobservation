# Deployment Checklist

## ✅ Step 1: Test Locally First

Before pushing to GitHub, test the app locally:

```bash
streamlit run app.py
```

**What to check:**
- ✅ App starts without errors
- ✅ Dashboard loads
- ✅ Can connect to Langfuse (no credential errors)
- ✅ Time period filters work
- ✅ Data displays correctly

## ✅ Step 2: Verify Files to Commit

**Files that SHOULD be committed:**
- ✅ `app.py`
- ✅ `langfuse_client.py`
- ✅ `requirements.txt`
- ✅ `Dockerfile`
- ✅ `.dockerignore`
- ✅ `.gitignore`
- ✅ `README.md`
- ✅ `AMPLIFY_SETUP.md`
- ✅ `.streamlit/secrets.toml.example` (example file, safe to commit)

**Files that SHOULD NOT be committed:**
- ❌ `.streamlit/secrets.toml` (contains real credentials)
- ❌ `.env` (if you created one)
- ❌ `__pycache__/` (auto-generated)
- ❌ Any virtual environment folders

## ✅ Step 3: Commit and Push

```bash
# Check what will be committed
git status

# Add all files (secrets.toml is already ignored)
git add .

# Commit with a descriptive message
git commit -m "Add ProjectManager usage dashboard with Langfuse integration"

# Push to GitHub
git push origin main
```

## ✅ Step 4: Verify Amplify Deployment

1. Go to AWS Amplify Console
2. Your app should automatically start building
3. Monitor the build logs
4. Once deployed, test the live URL

## ✅ Step 5: Verify Environment Variables

In Amplify Console → Environment Variables, confirm:
- `LANGFUSE_PUBLIC_KEY` is set
- `LANGFUSE_SECRET_KEY` is set
- `LANGFUSE_BASE_URL` is set to `https://us.cloud.langfuse.com`

## Troubleshooting

If the build fails:
- Check Amplify build logs
- Verify Dockerfile is in root directory
- Ensure all files are committed to GitHub

If the app won't connect to Langfuse:
- Double-check environment variables in Amplify
- Verify variable names are exact (case-sensitive)
- Ensure variables are marked as "Secure"

