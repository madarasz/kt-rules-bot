# Database Migration Scripts

## migrate_db.py

Updates the analytics database schema to add missing columns and tables.

### When to Use

Run this script when:
- You get "no such column" errors when starting the admin dashboard
- The codebase has been updated with new database columns
- You're upgrading from an older version of the bot

### Usage

```bash
python3 scripts/migrate_db.py
```

### What It Does

The script safely:
1. Checks if the database exists
2. Adds missing columns to existing tables (e.g., `quote_validation_score`, `quote_total_count`)
3. Creates missing tables (e.g., `invalid_quotes`)
4. Creates missing indexes for performance
5. Never deletes or modifies existing data

### Safe to Run Multiple Times

The script is idempotent - it checks if each change is needed before applying it, so it's safe to run multiple times.

### Example Output

```
============================================================
Analytics Database Migration
============================================================

🔍 Checking database at ./data/analytics.db
  ➕ Adding column queries.quote_validation_score
  ✅ Column queries.quote_total_count already exists

🔍 Checking indexes...
  ✅ Index idx_quote_validation_score already exists

🔍 Checking tables...
  ✅ Table invalid_quotes already exists

✅ Database is up to date! No migration needed.
```
