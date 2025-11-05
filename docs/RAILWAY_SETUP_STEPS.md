# Railway PostgreSQL Setup - Step by Step Guide

## Prerequisites

- Railway account (free tier works fine)
- GitHub repository connected to Railway
- Access to GitHub repository settings

---

## Step 1: Create PostgreSQL Database on Railway

### 1.1 Login to Railway

```
https://railway.app/
```

### 1.2 Navigate to Your Project

- Click on your existing project: **elder-friendly-form-pipeline**
- (If you don't have a project yet, create one and connect to GitHub)

### 1.3 Add PostgreSQL Database

1. Click **"New"** button (top right)
2. Select **"Database"**
3. Choose **"PostgreSQL"**
4. Wait ~30 seconds for provisioning

### 1.4 Verify Database is Running

- You should see a new PostgreSQL service card
- Status should show green checkmark ✅
- Click on the PostgreSQL card to view details

---

## Step 2: Get DATABASE_URL

### 2.1 Navigate to Variables Tab

1. Click on **PostgreSQL** service card
2. Click **"Variables"** tab
3. Find **DATABASE_URL** variable

### 2.2 Copy DATABASE_URL

```
postgresql://postgres:PASSWORD@HOST:PORT/railway
```

**Example:**

```
postgresql://postgres:abc123xyz@containers-us-west-123.railway.app:5432/railway
```

⚠️ **Important**: Keep this URL secret! Don't commit to Git.

### 2.3 Note the Connection Details

You'll also see individual variables:

- `PGHOST` - Database host
- `PGPORT` - Port (usually 5432)
- `PGUSER` - Username (usually postgres)
- `PGPASSWORD` - Password
- `PGDATABASE` - Database name (usually railway)

---

## Step 3: Add DATABASE_URL to GitHub Secrets

### 3.1 Navigate to GitHub Repository Settings

```
https://github.com/magicpro97/elder-friendly-form-pipeline/settings/secrets/actions
```

### 3.2 Create New Repository Secret

1. Click **"New repository secret"**
2. Name: `RAILWAY_DATABASE_URL`
3. Value: Paste the DATABASE_URL from Railway (Step 2.2)
4. Click **"Add secret"**

### 3.3 Verify Secret is Added

- You should see `RAILWAY_DATABASE_URL` in the list
- Value will be masked as `***`

### 3.4 (Optional) Add Other Secrets if Missing

Check if you have:

- ✅ `OPENAI_API_KEY` (for AI field extraction)
- ✅ `RAILWAY_DATABASE_URL` (just added)

---

## Step 4: Initialize Database Schema

You have **3 options** to initialize the schema:

### Option A: Via Railway Dashboard (Recommended for first time)

1. **Open Database Query Console**
   - Railway → PostgreSQL service → **"Query"** tab
   - Or click **"Connect"** → Use the web console

2. **Copy Schema SQL**
   - Open file: `db/schema.sql` from your repository
   - Copy entire contents (all ~150 lines)

3. **Execute Schema**
   - Paste into Railway Query console
   - Click **"Run"** or press `Ctrl+Enter`
   - Wait for success message

4. **Verify Tables Created**

   ```sql
   -- Run this query to verify
   SELECT table_name
   FROM information_schema.tables
   WHERE table_schema = 'public';
   ```

   Should return:
   - `forms`
   - `form_fields`

### Option B: Via Local Sync Script

1. **Set Environment Variable Locally**

   ```bash
   export DATABASE_URL="postgresql://postgres:PASSWORD@HOST:PORT/railway"
   ```

2. **Run Init Command**

   ```bash
   python src/sync_to_db.py --init-schema
   ```

3. **Expected Output**

   ```
   INFO: Connecting to PostgreSQL database...
   INFO: ✓ Connected successfully
   INFO: Initializing schema from db/schema.sql...
   INFO: ✓ Schema initialized successfully
   ```

### Option C: Via Railway CLI (Advanced)

1. **Install Railway CLI**

   ```bash
   npm install -g @railway/cli
   ```

2. **Login**

   ```bash
   railway login
   ```

3. **Link to Project**

   ```bash
   railway link
   ```

4. **Run Migration**

   ```bash
   railway run psql $DATABASE_URL < db/schema.sql
   ```

---

## Step 5: Sync Initial Forms to Database

### 5.1 Run Sync Script Locally

```bash
# Make sure DATABASE_URL is set
export DATABASE_URL="postgresql://..."

# Sync forms from all_forms.json
python src/sync_to_db.py --forms-file forms/all_forms.json
```

### 5.2 Expected Output

```
INFO: Loading forms from forms/all_forms.json...
INFO: Found 6 forms to sync
INFO: ✓ Upserted form: don_xin_viec (5 fields)
INFO: ✓ Upserted form: xac_nhan_cu_tru (4 fields)
INFO: ✓ Upserted form: giay_cam_ket (3 fields)
INFO: ✓ Upserted form: to_khai_tam_tru (6 fields)
INFO: ✓ Upserted form: don_xin_cap_lai (4 fields)
INFO: ✓ Upserted form: don_phan_to (5 fields)

✅ Sync completed successfully:
   - Total forms: 6
   - Synced: 6
   - Failed: 0

Database statistics:
   - manual: 5 forms
   - crawler: 1 forms
   - Total: 6 forms
   - Total fields: 27
```

### 5.3 Verify in Railway Dashboard

1. **Open Query Console**
2. **Run Query**

   ```sql
   SELECT form_id, title, source,
          array_length(aliases, 1) as alias_count
   FROM forms
   ORDER BY source, title;
   ```

3. **Expected Result**

   ```
   form_id              | title                      | source  | alias_count
   ---------------------|----------------------------|---------|------------
   don_phan_to          | ĐƠN PHẢN TỐ               | crawler | 2
   don_xin_cap_lai      | Đơn xin cấp lại           | manual  | 3
   don_xin_viec         | Đơn xin việc              | manual  | 2
   giay_cam_ket         | Giấy cam kết              | manual  | 2
   to_khai_tam_tru      | Tờ khai tạm trú           | manual  | 3
   xac_nhan_cu_tru      | Giấy xác nhận cư trú      | manual  | 2
   ```

---

## Step 6: Test Search Function

### 6.1 Test via Sync Script

```bash
python src/sync_to_db.py --test-search "đơn xin việc"
```

### 6.2 Expected Output

```
Testing search with query: 'đơn xin việc'
Found 2 results:
  1. Đơn xin việc
     Score: 1.000 | Source: manual | ID: don_xin_viec
  2. Đơn xin cấp lại
     Score: 0.600 | Source: manual | ID: don_xin_cap_lai
```

### 6.3 Test via SQL Query

```sql
-- Direct SQL query
SELECT * FROM search_forms('đơn', 0.3, 10);
```

---

## Step 7: Update Railway App Environment

### 7.1 Add Environment Variable to Your App

1. **Navigate to App Service** (not PostgreSQL)
   - Click on your FastAPI app service card
   - Go to **"Variables"** tab

2. **Add DATABASE_URL**
   - Click **"+ New Variable"**
   - Name: `DATABASE_URL`
   - Value: `${{Postgres.DATABASE_URL}}` (Railway will auto-inject)
   - Click **"Add"**

3. **Add USE_POSTGRES Flag**
   - Click **"+ New Variable"**
   - Name: `USE_POSTGRES`
   - Value: `true`
   - Click **"Add"**

4. **Redeploy App**
   - Click **"Deploy"** or app will auto-redeploy
   - Wait for deployment to complete

### 7.2 Verify App is Using PostgreSQL

1. **Check Logs**

   ```
   Railway → App service → "Deployments" → Latest deployment → View logs
   ```

2. **Look for**

   ```
   INFO: Loaded 6 forms from PostgreSQL
   INFO: Connected to PostgreSQL database
   ```

---

## Step 8: Test API Endpoints

### 8.1 Get Your App URL

Railway → App service → Copy the URL (e.g., `https://elder-friendly-form-pipeline.up.railway.app`)

### 8.2 Test Endpoints

**List all forms:**

```bash
curl https://your-app.railway.app/api/forms
```

**Search forms:**

```bash
curl "https://your-app.railway.app/api/forms/search?q=đơn"
```

**Get specific form:**

```bash
curl https://your-app.railway.app/api/forms/don_xin_viec
```

### 8.3 Expected Response

```json
{
  "ok": true,
  "count": 6,
  "forms": [
    {
      "form_id": "don_xin_viec",
      "title": "Đơn xin việc",
      "aliases": ["đơn xin việc", "job application"],
      "source": "manual",
      "fields": [...]
    }
  ]
}
```

---

## Step 9: Test GitHub Actions Workflow

### 9.1 Trigger Manual Workflow

1. **Navigate to Actions Tab**

   ```
   https://github.com/magicpro97/elder-friendly-form-pipeline/actions
   ```

2. **Select Workflow**
   - Click **"Process Forms and Sync to Database"**

3. **Run Workflow**
   - Click **"Run workflow"** dropdown
   - Branch: `main`
   - Click green **"Run workflow"** button

### 9.2 Monitor Workflow

1. **Watch Progress**
   - Click on the running workflow
   - See each step execute in real-time

2. **Expected Steps** (all should ✅)
   - ✅ Checkout repository
   - ✅ Set up Python 3.11
   - ✅ Install dependencies
   - ✅ Process forms from crawled files
   - ✅ Merge forms
   - ✅ **Sync to PostgreSQL** ⭐
   - ✅ **Test search function** ⭐
   - ✅ Upload processed forms
   - ✅ Commit changes (if any)
   - ✅ Create summary

3. **Check Summary**
   - Scroll down to see "Form Processing Summary"
   - Should show statistics and completed tasks

### 9.3 Verify Database Updated

**Check Railway Query Console:**

```sql
SELECT COUNT(*) as total_forms FROM forms;
SELECT COUNT(*) as total_fields FROM form_fields;
```

---

## Step 10: Verify Automatic Trigger (Optional)

### 10.1 Wait for Daily Crawler

The workflow will automatically trigger after "Daily Vietnamese Form Crawler" completes (00:00 UTC).

### 10.2 Or Manually Trigger Crawler

1. **Run Crawler Workflow**

   ```
   GitHub Actions → "Daily Vietnamese Form Crawler" → Run workflow
   ```

2. **Wait for Completion**

3. **Check if Form Processing Triggered**
   - Should automatically start after crawler completes
   - Check Actions tab for new "Process Forms and Sync to Database" run

---

## Troubleshooting

### Issue 1: Connection Timeout

**Error:**

```
psycopg2.OperationalError: could not connect to server
```

**Solution:**

1. Check DATABASE_URL is correct
2. Verify PostgreSQL service is running on Railway
3. Check network/firewall (unlikely with Railway)

### Issue 2: Schema Already Exists

**Error:**

```
relation "forms" already exists
```

**Solution:**

- Schema already initialized, skip Step 4
- Or drop and recreate: `DROP TABLE IF EXISTS forms, form_fields CASCADE;`

### Issue 3: GitHub Secret Not Working

**Error in Actions:**

```
DATABASE_URL not found in environment variables
```

**Solution:**

1. Verify secret name is exactly `RAILWAY_DATABASE_URL`
2. Re-add the secret with correct value
3. Re-run workflow

### Issue 4: API Returns Empty Forms

**Error:**

```json
{"ok": true, "count": 0, "forms": []}
```

**Solution:**

1. Check if forms are in database: `SELECT COUNT(*) FROM forms;`
2. If 0, run sync script: `python src/sync_to_db.py`
3. Check app logs for errors

---

## Verification Checklist

- [ ] PostgreSQL database created on Railway
- [ ] DATABASE_URL copied and saved securely
- [ ] GitHub secret `RAILWAY_DATABASE_URL` added
- [ ] Database schema initialized (tables created)
- [ ] Initial forms synced (6 forms in database)
- [ ] Search function tested successfully
- [ ] App environment variables updated (DATABASE_URL, USE_POSTGRES)
- [ ] API endpoints returning data
- [ ] GitHub Actions workflow runs successfully
- [ ] No errors in Railway app logs

---

## Success Criteria

✅ **All green if:**

1. **Database has data**

   ```sql
   SELECT COUNT(*) FROM forms;  -- Returns 6+
   ```

2. **API works**

   ```bash
   curl https://your-app.railway.app/api/forms | jq '.count'
   # Returns: 6
   ```

3. **Search works**

   ```bash
   curl "https://your-app.railway.app/api/forms/search?q=đơn" | jq '.results | length'
   # Returns: 2+
   ```

4. **GitHub Actions passes**
   - All steps green ✅
   - Summary shows "Synced to PostgreSQL"

---

## Next Steps After Setup

1. **Monitor Daily Syncs**
   - Check GitHub Actions logs daily
   - Verify new forms are being added

2. **Performance Optimization** (if needed)
   - Add more indexes
   - Enable query result caching
   - Optimize search relevance scoring

3. **Backup Strategy**
   - Railway has automatic backups
   - Or setup manual backups via CLI: `railway run pg_dump`

4. **Scale Up** (if needed)
   - Railway free tier: 500MB storage
   - Upgrade to Pro for more storage/connections

---

## Support

- **Railway Docs**: <https://docs.railway.app/databases/postgresql>
- **Project Issues**: <https://github.com/magicpro97/elder-friendly-form-pipeline/issues>
- **PostgreSQL Docs**: <https://www.postgresql.org/docs/current/>

---

🎉 **Congratulations!** Your form processing pipeline is now fully automated with PostgreSQL storage!
