"""
Run this ONCE to copy your local data.db into Supabase PostgreSQL.

Usage:
    1. Set DATABASE_URL environment variable to your Supabase connection string
       Example: set DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres
    2. Run: python migrate_to_supabase.py
"""
import sqlite3, os, sys

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: Set DATABASE_URL environment variable first.")
    sys.exit(1)

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print("ERROR: Run 'pip install psycopg2-binary' first.")
    sys.exit(1)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
if not os.path.exists(DB_PATH):
    print("ERROR: data.db not found.")
    sys.exit(1)

TABLES = ["stats", "player_entries", "battle_plans", "daily_checkins",
          "condition_tasks", "admin_scale_2d", "shared_goals"]

sqlite_conn = sqlite3.connect(DB_PATH)
sqlite_conn.row_factory = sqlite3.Row

pg_conn = psycopg2.connect(DATABASE_URL)
pg_conn.autocommit = False

# Import the app's init_db to create tables in PostgreSQL
print("Creating tables in Supabase...")
import importlib.util, types, unittest.mock

# Mock streamlit so we can import the module
import sys
mock_st = types.ModuleType("streamlit")
mock_st.set_page_config = lambda **k: None
mock_st.secrets = {"DATABASE_URL": DATABASE_URL}
mock_st.cache_data = lambda f=None, **k: (f if f else lambda g: g)
mock_st.cache_resource = lambda f=None, **k: (f if f else lambda g: g)
sys.modules["streamlit"] = mock_st

# We'll just run init_db via the app's own function
os.environ["DATABASE_URL"] = DATABASE_URL

spec = importlib.util.spec_from_file_location("app", DB_PATH.replace("data.db", "streamlit_app.py"))
try:
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    app_module.init_db()
    print("Tables created.")
except Exception as e:
    print(f"Could not auto-create tables via app: {e}")
    print("Please run the app once with DATABASE_URL set to create tables automatically.")

# Copy data table by table
with pg_conn:
    cur = pg_conn.cursor()
    for table in TABLES:
        rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  {table}: empty, skipping")
            continue

        cols = rows[0].keys()
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)

        cur.execute(f"DELETE FROM {table}")  # clear first to avoid duplicates

        for row in rows:
            try:
                cur.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    tuple(row)
                )
            except Exception as e:
                print(f"  Warning on {table}: {e}")

        print(f"  {table}: {len(rows)} rows copied")

pg_conn.close()
sqlite_conn.close()
print("\nMigration complete!")
