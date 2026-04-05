import streamlit as st
import sqlite3
import os
from datetime import datetime, timedelta, date as date_type

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mission Control — 2D",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE ABSTRACTION  (SQLite locally · PostgreSQL in cloud via DATABASE_URL)
# ─────────────────────────────────────────────────────────────────────────────
def _db_url():
    try:
        return st.secrets.get("DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
    except Exception:
        return os.environ.get("DATABASE_URL", "")


class _PGWrapper:
    """Wraps psycopg2 to look like a sqlite3 connection."""

    def __init__(self, url):
        import psycopg2, psycopg2.extras
        self._conn = psycopg2.connect(url)
        self._extras = psycopg2.extras

    @staticmethod
    def _translate(sql):
        sql = sql.replace("?", "%s")
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        if "INSERT OR IGNORE" in sql:
            sql = sql.replace("INSERT OR IGNORE", "INSERT")
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return sql

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=self._extras.RealDictCursor)
        cur.execute(self._translate(sql), params if params else None)
        return cur

    def table_columns(self, table):
        cur = self.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,)
        )
        return [r["column_name"] for r in cur.fetchall()]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _v, _tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


def _table_columns(conn, table):
    """Return list of column names for a table (works for both SQLite and PG)."""
    if isinstance(conn, _PGWrapper):
        return conn.table_columns(table)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]

# ─────────────────────────────────────────────────────────────────────────────
# PLAYERS
# ─────────────────────────────────────────────────────────────────────────────
PLAYER_INFO = {
    "Mareks": {"color": "#7aa2f7", "emoji": "⚡", "bg": "#0b1628", "alt": "#3d5a80"},
    "Karen":  {"color": "#f7a8d8", "emoji": "🌸", "bg": "#280b1a", "alt": "#6d2b4e"},
}

# ─────────────────────────────────────────────────────────────────────────────
# ALL 12 CONDITIONS
# ─────────────────────────────────────────────────────────────────────────────
CONDITIONS_ORDER = [
    "Power", "Power Change", "Affluence", "Normal", "Emergency",
    "Danger", "Non-Existence", "Liability", "Doubt", "Enemy", "Treason", "Confusion",
]

CONDITION_COLOR = {
    "Power":         "#FFD700",
    "Power Change":  "#00BCD4",
    "Affluence":     "#27ae60",
    "Normal":        "#2980b9",
    "Emergency":     "#e67e22",
    "Danger":        "#c0392b",
    "Non-Existence": "#7f8c8d",
    "Liability":     "#d35400",
    "Doubt":         "#f39c12",
    "Enemy":         "#922b21",
    "Treason":       "#6c1a47",
    "Confusion":     "#2c3e50",
}

CONDITION_EMOJI = {
    "Power":         "👑",
    "Power Change":  "🔄",
    "Affluence":     "🚀",
    "Normal":        "✅",
    "Emergency":     "⚠️",
    "Danger":        "🔴",
    "Non-Existence": "👻",
    "Liability":     "🔶",
    "Doubt":         "🤔",
    "Enemy":         "⚔️",
    "Treason":       "💀",
    "Confusion":     "🌀",
}

CONDITION_FORMULA = {
    "Power": [
        "Don't disconnect — maintain all communication and relationships.",
        "Write up your job fully so it can be properly handed to the next person.",
    ],
    "Power Change": [
        "Assume the position but make NO changes yet.",
        "Keep your eyes open — learn exactly how the job works.",
        "Find out how things are running and what is working.",
        "Identify what made things better and strengthen it.",
        "Find what worsened and remove it.",
        "Follow the exact same actions as your predecessor.",
        "Sign nothing your predecessor wouldn't have signed.",
        "Don't change a single standing order.",
        "Study all existing orders thoroughly.",
        "Write up fully what the previous person was doing.",
    ],
    "Affluence": [
        "Economize — cut unnecessary expenses, avoid new debt commitments.",
        "Pay every bill — get and pay every penny you owe.",
        "Invest in what enhances your ability to deliver.",
        "Find out what caused the Affluence and strengthen it.",
    ],
    "Normal": [
        "Don't change anything that is working.",
        "Identify every improvement and find what caused it — do more of that.",
        "When anything worsens slightly, quickly find out why and fix it.",
    ],
    "Emergency": [
        "Promote — make yourself, your work, your product known.",
        "Change your operating basis — what you are doing led to this, change it.",
        "Economize — spend less, reduce all waste.",
        "Get ready to deliver — have your product ready.",
        "Be more disciplined — be on time, focused, eliminate waste.",
    ],
    "Danger": [
        "Bypass normal routine — handle things personally.",
        "Handle the situation and any immediate danger.",
        "Tell yourself you are in a Danger Condition.",
        "Get in your own ethics — find what is not ethical and correct it.",
        "Reorganize your life so the dangerous situation does not continue.",
        "Create firm rules to find and prevent this situation in future.",
    ],
    "Non-Existence": [
        "Find a way to communicate with the person or group you need to connect with.",
        "Make yourself known to the people.",
        "Discover what they need or want from you.",
        "Do, produce and/or present what they need and want.",
    ],
    "Liability": [
        "Decide whether you are for or against the survival of the group.",
        "If for — make up the damage you have done by your own effort.",
        "Apply formulas for conditions below this one.",
        "Request rejoining the group by petition.",
        "Get a sponsor from within the group who will vouch for you.",
        "Be approved back in by the group.",
    ],
    "Doubt": [
        "Inform yourself honestly of the actual intentions and activities of the group — no rumors.",
        "Examine the statistics of the individual or group.",
        "Decide: attack, help, or leave — based on greatest benefit for greatest number.",
        "Examine your own intentions and goals honestly.",
        "Examine your own statistics honestly.",
        "Join or remain with the one that benefits the greatest number — announce it openly.",
        "Do everything possible to improve the group you joined.",
        "Work up the conditions in the new group if you changed sides.",
    ],
    "Enemy": [
        "Find out who you really are.",
    ],
    "Treason": [
        "Find out that you are — identify your actual position and role.",
    ],
    "Confusion": [
        "Find out WHERE you are.",
        "Do a Locational — walk around, point at objects, say 'Look at that [object]', acknowledge.",
        "Compare where you are to other areas where you used to be.",
        "Repeat step 1.",
    ],
}

CONDITION_XP = {
    "Power": 100, "Power Change": 90, "Affluence": 80, "Normal": 60,
    "Emergency": 40, "Danger": 30, "Non-Existence": 20,
    "Liability": 15, "Doubt": 10, "Enemy": 5, "Treason": 3, "Confusion": 1,
}

XP_LEVELS = [
    (500, "Power"),
    (400, "Power Change"),
    (300, "Affluence"),
    (200, "Normal"),
    (150, "Emergency"),
    (100, "Danger"),
    (70,  "Non-Existence"),
    (50,  "Liability"),
    (30,  "Doubt"),
    (20,  "Enemy"),
    (10,  "Treason"),
    (0,   "Confusion"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 2D ADMIN SCALE — PRE-POPULATED WITH YOUR DATA
# ─────────────────────────────────────────────────────────────────────────────
ADMIN_SCALE_2D_DEFAULTS = [
    ("Goal", """⭐ Be OTVIII
⭐ Class V C/Ses with all specialities
⭐ Ethics Officers
⭐ Finish Basics and ACCs
⭐ Power FSM
⭐ Have super health, body and amazing fighting skills
⭐ Learn Latvian, German, Spanish and Russian"""),

    ("Purpose", """🎯 Have financial freedom
🎯 Have real estate in Germany, Italy, Latvia and Guatemala generating more income than expenses
🎯 Have a business — Coffee from Guatemala, Guatemalan food, marketing
🎯 Make money with businesses and real estate
🎯 Have a religious wedding in Freewinds
🎯 Publish our books, music, and Latvian dictionaries"""),

    ("Policy", """📋 Always be in Scientology — have an org, mission, group or course.

📋 Apply ARC and be willing to communicate. Have admiration for each other every day. Communicate with purpose to handle and achieve good things.

📋 Plan our month at the beginning or end of the month for goals to achieve that month. Plan every week our goals for the week. Be pro-survival and never waste time."""),

    ("Plans", """📌 Get Karen to Germany legally
📌 Have Garu with us
📌 Pay debt: 11,300 euros
📌 Pay OT VI and VII: 38,000 dollars
📌 Pay Mareks till OT V: 24,000 euros
📌 Send Mareks folders to AO
📌 Finish our Basics with conferences
📌 Buy E-Meter: 9,000 euros
📌 Pay Scholarship to Class V: 7,000 euros
📌 Establish 5,000 euros / monthly income
📌 Training up to Class V for Mareks
📌 C/S training for Karen"""),

    ("Programs", """━━━ GET KAREN TO GERMANY (Legal) ━━━
  • Apostille for Marriage Certificate
  • Apostille for Birth Certificate
  • Passport 5-year renewal
  • Copies of marriage and birth certificates
  • Translation of Marriage Cert to German
  • Translation of Birth Cert to English & German
  • Insurance for Karen
  • Buy ticket (~1,000 euros)
  • Buy suitcases

━━━ SEND MAREKS FOLDERS TO AO ━━━
  • Get all admin done if needed
  • Reunite all papers and folders
  • Pack and weigh
  • Make cost estimate
  • Pay delivery and send to AO

━━━ REAL ESTATE — 5,000 euros/month ━━━
  • Establish 2 rental apartments
  • Check market: Latvia, Italy, Greece, Germany
  • Decide focus market and make budget
  • Create dedicated real estate account
  • Build credit score
  • Get a loan

━━━ BUSINESS — COFFEE & FOOD ━━━
  • Get contact in Guatemala for quality coffee
  • Research export prices and logistics to Germany
  • Get branding and packaging sorted
  • Ask Zinder (or find someone) to help with export to Germany
  • Register food business, decide name and menu
  • Set prices, promote, cook on request, deliver by bicycle

━━━ PAY SCHOLARSHIP (7k) + E-METER (9k) ━━━
  • Set up monthly payment plan of 1,000 euros
  • Complete in 12 months

━━━ TRAINING — Class V (Mareks) / C/S (Karen) ━━━
  • Pay Scholarship to Dublin and E-meter
  • Get prices for housing and food in Dublin
  • Research full-time course schedule
  • Budget the months to be spent there

━━━ PAY DEBT (11,300 euros) ━━━
  • List all creditors and amounts
  • Establish monthly payments of 750 euros
  • Complete in 15 months

━━━ PAY OT VI & VII (38,000 dollars) ━━━
  • Establish monthly payments of 150 euros
  • Increase once out of training

━━━ PAY MAREKS OT V (24,000 euros) ━━━
  • Establish monthly payments of 150 euros
  • Increase once out of training

━━━ FINISH BASICS ━━━
  • Karen: Finish Factors — 1 lesson/week
  • Mareks: Finish Dianetics — 1 lesson/week
  • Pay and finish PDC (Mareks)
  • Pay and finish Phoenix (Karen)
  • Pay and finish Factors & Phoenix (Mareks)

━━━ PUBLISH OUR ART ━━━
  • Create and publish our music
  • Write and publish Mareks' books
  • Create and publish Latvian dictionary
  • Create and publish videos

━━━ FREEWINDS WEDDING ━━━
  • Get prices, make budget, set date
  • Invite close friends and family
  • Plan Postulate / 2D / Artist convention with org board

━━━ LIFETIME IAS (500 euros — Guatemala) ━━━
  • Make the payment in Guatemala

━━━ LEARN LANGUAGES (German, Latvian, Russian, Spanish + English) ━━━
  • Daily Duolingo — 15 minutes each
  • Create grammar/vocabulary notebook for Latvian
  • Watch movies and listen to music in target language
  • Use grammar websites, books, and videos

━━━ HEALTHY BODY ━━━
  • 10,000 steps every day
  • 2 liters of water daily (Karen); 1 cup (Mareks)
  • No sugar — only fruits and natural foods
  • No wheat — use almond flour"""),

    ("Projects", """🔧 Active projects right now:
  • Karen's German visa and travel prep
  • Send Mareks AO folders
  • First rental property research
  • Debt payment plan (750 EUR/month)
  • Daily Duolingo habit"""),

    ("Orders", "📝 Daily and weekly orders are tracked in the Battle Plans tab."),

    ("Ideal Scene", """✨ Both Mareks and Karen are Clear and on their OT levels.
✨ We own rental properties generating 5,000+ euros/month passively.
✨ We are trained Class V C/Ses with our own auditing practice.
✨ We live between Germany, Latvia and Guatemala.
✨ In perfect health — active, strong, fighting skills, 4 languages fluent.
✨ Our music, books, and Latvian dictionaries are published.
✨ Freewinds wedding celebrated with family and close friends.
✨ Lifetime IAS members."""),

    ("Statistics", """📊 Monthly income (EUR)
📊 Properties owned
📊 Courses completed
📊 Book pages written
📊 Languages at B1+
📊 Average daily steps (Karen)
📊 Debt remaining (EUR)
📊 Duolingo streak (days)"""),

    ("Valuable Final Products", """🏆 Financial freedom through real estate and business
🏆 Both Clear and on OT levels — trained Class V C/Ses
🏆 Published authors, musicians, and Latvian dictionary creators
🏆 Freewinds wedding celebrated
🏆 Healthy, active, multilingual life together"""),
]

ADMIN_LEVEL_COLORS = {
    "Goal":                    "#FFD700",
    "Purpose":                 "#00BCD4",
    "Policy":                  "#27ae60",
    "Plans":                   "#2980b9",
    "Programs":                "#e67e22",
    "Projects":                "#c0392b",
    "Orders":                  "#7f8c8d",
    "Ideal Scene":             "#9b59b6",
    "Statistics":              "#3498db",
    "Valuable Final Products": "#1abc9c",
}

ADMIN_LEVEL_EMOJI = {
    "Goal":                    "⭐",
    "Purpose":                 "🎯",
    "Policy":                  "📋",
    "Plans":                   "📌",
    "Programs":                "🗺️",
    "Projects":                "🔧",
    "Orders":                  "📝",
    "Ideal Scene":             "✨",
    "Statistics":              "📊",
    "Valuable Final Products": "🏆",
}

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────
def get_db():
    url = _db_url()
    if url:
        return _PGWrapper(url)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT    NOT NULL,
                stat_id     INTEGER NOT NULL,
                week_date   TEXT    NOT NULL,
                value       REAL    NOT NULL,
                UNIQUE(player_name, stat_id, week_date),
                FOREIGN KEY(stat_id) REFERENCES stats(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS battle_plans (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name    TEXT NOT NULL DEFAULT 'Mareks',
                plan_text      TEXT NOT NULL,
                plan_type      TEXT NOT NULL DEFAULT 'daily',
                week_date      TEXT NOT NULL,
                done           INTEGER DEFAULT 0,
                completed_date TEXT,
                created_at     TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_checkins (
                player_name  TEXT NOT NULL,
                checkin_date TEXT NOT NULL,
                PRIMARY KEY (player_name, checkin_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS condition_tasks (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name    TEXT NOT NULL,
                stat_name      TEXT NOT NULL,
                condition_name TEXT NOT NULL,
                step_num       INTEGER NOT NULL,
                step_text      TEXT NOT NULL,
                done           INTEGER DEFAULT 0,
                week_date      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_scale_2d (
                level_name TEXT PRIMARY KEY,
                content    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shared_goals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                title          TEXT NOT NULL,
                description    TEXT,
                target_amount  REAL DEFAULT 50000,
                currency       TEXT DEFAULT 'EUR',
                current_amount REAL DEFAULT 0
            )
        """)

        # Migrate old battle_plans table (add missing columns if needed)
        cols = _table_columns(conn, "battle_plans")
        if "player_name" not in cols:
            try:
                conn.execute("ALTER TABLE battle_plans ADD COLUMN player_name TEXT DEFAULT 'Mareks'")
            except Exception:
                pass
        if "completed_date" not in cols:
            try:
                conn.execute("ALTER TABLE battle_plans ADD COLUMN completed_date TEXT")
            except Exception:
                pass

        # Seed 2D Admin Scale
        if conn.execute("SELECT COUNT(*) as c FROM admin_scale_2d").fetchone()["c"] == 0:
            for level_name, content in ADMIN_SCALE_2D_DEFAULTS:
                conn.execute(
                    "INSERT OR IGNORE INTO admin_scale_2d (level_name, content) VALUES (?,?)",
                    (level_name, content)
                )

        # Seed shared goal
        if conn.execute("SELECT COUNT(*) as c FROM shared_goals").fetchone()["c"] == 0:
            conn.execute("""
                INSERT INTO shared_goals (title, description, target_amount, currency, current_amount)
                VALUES ('First Rental Property',
                        'Save enough together to buy our first rental property',
                        50000, 'EUR', 0)
            """)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_condition(prev, curr):
    if prev is None or prev == 0:
        return "Non-Existence"
    pct = ((curr - prev) / prev) * 100
    if pct > 20:     return "Affluence"
    elif pct >= 0:   return "Normal"
    elif pct >= -20: return "Emergency"
    elif curr > 0:   return "Danger"
    else:            return "Non-Existence"

def this_monday():
    today = datetime.today()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

def today_str():
    return datetime.today().strftime("%Y-%m-%d")

def _streak_from_set(dates_set):
    if not dates_set:
        return 0
    today = date_type.today()
    start = today if today.strftime("%Y-%m-%d") in dates_set else today - timedelta(days=1)
    if start.strftime("%Y-%m-%d") not in dates_set:
        return 0
    streak, check = 0, start
    while check.strftime("%Y-%m-%d") in dates_set:
        streak += 1
        check -= timedelta(days=1)
    return streak

def get_streak(player_name):
    with get_db() as conn:
        dates_set = {r["checkin_date"] for r in conn.execute(
            "SELECT checkin_date FROM daily_checkins WHERE player_name=?", (player_name,)
        ).fetchall()}
    return _streak_from_set(dates_set)

def get_bp_streak(player_name):
    with get_db() as conn:
        dates_set = {r["completed_date"] for r in conn.execute(
            "SELECT DISTINCT completed_date FROM battle_plans "
            "WHERE player_name=? AND done=1 AND completed_date IS NOT NULL",
            (player_name,)
        ).fetchall()}
    return _streak_from_set(dates_set)

def get_player_xp(player_name):
    xp = 0
    with get_db() as conn:
        xp += conn.execute(
            "SELECT COUNT(*) as c FROM battle_plans WHERE player_name=? AND done=1",
            (player_name,)
        ).fetchone()["c"] * 10
        xp += conn.execute(
            "SELECT COUNT(*) as c FROM condition_tasks WHERE player_name=? AND done=1",
            (player_name,)
        ).fetchone()["c"] * 15
        xp += get_streak(player_name) * 5
        for stat in conn.execute("SELECT id FROM stats").fetchall():
            entries = conn.execute(
                "SELECT value FROM player_entries WHERE player_name=? AND stat_id=? "
                "ORDER BY week_date DESC LIMIT 2",
                (player_name, stat["id"])
            ).fetchall()
            if entries:
                curr = entries[0]["value"]
                prev = entries[1]["value"] if len(entries) > 1 else None
                xp += CONDITION_XP.get(get_condition(prev, curr), 0)
    return xp

def xp_to_level(xp):
    for threshold, level in XP_LEVELS:
        if xp >= threshold:
            return level, CONDITION_COLOR[level]
    return "Confusion", CONDITION_COLOR["Confusion"]

def xp_progress(xp):
    thresholds = sorted([t for t, _ in XP_LEVELS])
    prev_t, next_t = 0, thresholds[-1]
    for t in thresholds:
        if xp < t:
            next_t = t
            break
        prev_t = t
    rng = next_t - prev_t
    pct = ((xp - prev_t) / rng * 100) if rng > 0 else 100
    return prev_t, next_t, min(100.0, pct)

def get_player_stat_conditions(player_name):
    """Returns list of (stat_name, value, condition) for all stats with data."""
    results = []
    with get_db() as conn:
        for stat in conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall():
            entries = conn.execute(
                "SELECT value FROM player_entries WHERE player_name=? AND stat_id=? "
                "ORDER BY week_date DESC LIMIT 2",
                (player_name, stat["id"])
            ).fetchall()
            if entries:
                curr = entries[0]["value"]
                prev = entries[1]["value"] if len(entries) > 1 else None
                results.append((stat["name"], curr, get_condition(prev, curr)))
    return results

def get_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    .stApp { background-color: #08080f; color: #ddd; }
    .block-container { padding-top: 1rem; max-width: 1400px; }
    h1, h2, h3, h4 { color: white !important; }
    label { color: #bbb !important; }

    .player-card {
        border-radius: 14px;
        padding: 20px 22px;
        margin: 6px 0 12px;
        position: relative;
        overflow: hidden;
        border: 1px solid #ffffff0d;
    }
    .player-card-bar {
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
    }
    .xp-bar-outer {
        background: #ffffff12;
        border-radius: 99px;
        height: 10px;
        margin: 5px 0 2px;
        overflow: hidden;
    }
    .xp-bar-inner { height: 100%; border-radius: 99px; }

    .goal-card {
        background: linear-gradient(135deg, #0d1726 0%, #1a0d26 100%);
        border-radius: 14px;
        padding: 18px 22px;
        margin-bottom: 14px;
        border: 1px solid #ffffff10;
    }
    .goal-bar-outer {
        background: #ffffff12;
        border-radius: 99px;
        height: 14px;
        margin: 8px 0 4px;
        overflow: hidden;
    }
    .goal-bar-inner {
        height: 100%;
        border-radius: 99px;
        background: linear-gradient(90deg, #7aa2f7, #27ae60);
    }

    .condition-rung {
        padding: 5px 12px;
        border-radius: 0 8px 8px 0;
        margin: 2px 0;
        font-size: 0.83em;
        font-weight: bold;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-left: 4px solid;
    }
    .condition-banner {
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        color: white;
        font-size: 1.4em;
        font-weight: bold;
        margin: 12px 0;
    }
    .condition-task-header {
        border-left: 4px solid;
        border-radius: 0 8px 8px 0;
        padding: 7px 12px;
        margin: 12px 0 4px;
        font-weight: bold;
        font-size: 0.9em;
    }
    .formula-complete {
        border-radius: 8px;
        padding: 10px;
        text-align: center;
        margin: 8px 0;
        font-weight: bold;
    }
    .admin-section {
        background: #0d0d1c;
        border-radius: 10px;
        padding: 14px 16px;
        margin: 6px 0;
        border: 1px solid #1a1a2e;
        border-left: 3px solid;
    }
    .type-header {
        font-size: 0.78em;
        font-weight: bold;
        letter-spacing: 2px;
        margin: 14px 0 4px;
    }
    .streak-box {
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 12px;
        border: 1px solid;
    }
    .stat-mini-card {
        border-radius: 10px;
        padding: 12px;
        text-align: center;
        margin: 4px 0;
        border: 1px solid;
    }

    .stTabs [data-baseweb="tab"] {
        background: #12121e;
        color: #888;
        border-radius: 8px 8px 0 0;
        padding: 8px 18px;
    }
    .stTabs [aria-selected="true"] {
        background: #1e1e3e !important;
        color: white !important;
    }
    .stTextInput input, .stNumberInput input {
        background: #12121e !important;
        color: white !important;
        border-color: #2a2a3e !important;
    }
    div[data-testid="stForm"] {
        background: #0d0d1c;
        border-radius: 10px;
        padding: 14px;
        border: 1px solid #1a1a2e;
    }
    .stCheckbox label { color: #ccc !important; }
    .stExpander { background: #0d0d1c !important; border-color: #1a1a2e !important; }
    </style>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD TAB
# ─────────────────────────────────────────────────────────────────────────────
def tab_dashboard():
    # ── Shared Goal ────────────────────────────────────────────────────────
    with get_db() as conn:
        goal = conn.execute("SELECT * FROM shared_goals LIMIT 1").fetchone()

    if goal:
        pct = min(100.0, goal["current_amount"] / max(goal["target_amount"], 1) * 100)
        st.markdown(f"""
        <div class="goal-card">
            <div style="color:#7aa2f7;font-size:0.72em;letter-spacing:3px;font-weight:bold">
                🏠 SHARED MISSION
            </div>
            <div style="color:white;font-size:1.45em;font-weight:bold;margin:4px 0">
                {goal['title']}
            </div>
            <div style="color:#555;font-size:0.87em;margin-bottom:10px">{goal['description']}</div>
            <div style="color:#aaa;font-size:0.85em">
                €{goal['current_amount']:,.0f} saved &nbsp;/&nbsp; €{goal['target_amount']:,.0f} goal
            </div>
            <div class="goal-bar-outer">
                <div class="goal-bar-inner" style="width:{pct:.1f}%"></div>
            </div>
            <div style="color:#7aa2f7;font-size:0.78em;text-align:right;margin-top:2px">
                {pct:.1f}% of goal reached
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("💰 Update savings amount"):
            with st.form("update_savings_form"):
                new_amt = st.number_input(
                    "Current savings (EUR)", value=float(goal["current_amount"]),
                    min_value=0.0, step=100.0
                )
                if st.form_submit_button("Update", use_container_width=True):
                    with get_db() as conn:
                        conn.execute(
                            "UPDATE shared_goals SET current_amount=? WHERE id=?",
                            (new_amt, goal["id"])
                        )
                    st.rerun()

    # ── Player Cards ───────────────────────────────────────────────────────
    col_m, col_k = st.columns(2)

    for col, player_name in zip([col_m, col_k], ["Mareks", "Karen"]):
        pinfo    = PLAYER_INFO[player_name]
        streak   = get_streak(player_name)
        bp_str   = get_bp_streak(player_name)
        xp       = get_player_xp(player_name)
        level, level_color = xp_to_level(xp)
        _, next_xp, xp_pct = xp_progress(xp)

        with get_db() as conn:
            checked_in = conn.execute(
                "SELECT 1 FROM daily_checkins WHERE player_name=? AND checkin_date=?",
                (player_name, today_str())
            ).fetchone()

        stat_conds = get_player_stat_conditions(player_name)
        badges = "".join(
            f"<span style='background:{CONDITION_COLOR[cond]}22;"
            f"border:1px solid {CONDITION_COLOR[cond]}44;"
            f"color:{CONDITION_COLOR[cond]};padding:2px 8px;border-radius:10px;"
            f"font-size:0.73em;font-weight:bold;display:inline-block;margin:2px'>"
            f"{CONDITION_EMOJI[cond]} {name}: {cond}</span>"
            for name, _, cond in stat_conds
        ) or "<span style='color:#333;font-size:0.82em'>No stats yet — add in Stats tab</span>"

        fire_login = ("🔥" * min(streak, 7)) if streak else "💤"
        fire_plan  = ("🔥" * min(bp_str, 7)) if bp_str else "—"
        ci_badge   = "✅ CHECKED IN TODAY" if checked_in else "⬜ CHECK IN TO KEEP STREAK"

        with col:
            st.markdown(f"""
            <div class="player-card" style="background:{pinfo['bg']}">
                <div class="player-card-bar"
                     style="background:linear-gradient(90deg,{pinfo['color']},{pinfo['color']}33)">
                </div>
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
                    <div>
                        <span style="font-size:1.7em">{pinfo['emoji']}</span>
                        <span style="color:{pinfo['color']};font-size:1.25em;font-weight:bold;
                                     margin-left:8px">{player_name}</span>
                        <span style="background:{level_color};color:#000;font-size:0.63em;
                                     font-weight:bold;padding:2px 9px;border-radius:10px;
                                     margin-left:6px;vertical-align:middle">
                            {level.upper()}
                        </span>
                    </div>
                    <div style="color:#555;font-size:0.7em;text-align:right;padding-top:4px">
                        {ci_badge}
                    </div>
                </div>

                <div style="margin-bottom:10px">
                    <div style="color:#666;font-size:0.77em">
                        ⚡ {xp} XP &nbsp;—&nbsp; next level at {next_xp} XP
                    </div>
                    <div class="xp-bar-outer">
                        <div class="xp-bar-inner"
                             style="width:{xp_pct:.0f}%;background:{level_color}">
                        </div>
                    </div>
                </div>

                <div style="margin-bottom:12px;font-size:0.87em">
                    <span style="color:#777">📅 Login streak:</span>
                    <span style="color:{pinfo['color']};font-weight:bold">
                        &nbsp;{streak}d &nbsp;{fire_login}
                    </span>
                    &emsp;
                    <span style="color:#777">✅ Plan streak:</span>
                    <span style="color:{pinfo['color']};font-weight:bold">
                        &nbsp;{bp_str}d &nbsp;{fire_plan}
                    </span>
                </div>

                <div style="line-height:1.8">{badges}</div>
            </div>
            """, unsafe_allow_html=True)

            if not checked_in:
                if st.button(
                    f"✅ Check In Today — {player_name}",
                    key=f"checkin_{player_name}",
                    use_container_width=True
                ):
                    with get_db() as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO daily_checkins VALUES (?,?)",
                            (player_name, today_str())
                        )
                    st.rerun()
            else:
                st.success(f"🔥 Streak alive! Come back tomorrow to keep it going!")

    # ── Conditions Ladder ──────────────────────────────────────────────────
    st.markdown("---")
    left, right = st.columns([1.6, 2.4])

    with left:
        st.markdown("**CONDITIONS LADDER**")

        player_conds = {p: set() for p in PLAYER_INFO}
        for pname in PLAYER_INFO:
            for _, _, cond in get_player_stat_conditions(pname):
                player_conds[pname].add(cond)

        for cond in CONDITIONS_ORDER:
            color   = CONDITION_COLOR[cond]
            emoji   = CONDITION_EMOJI[cond]
            markers = "".join(
                f"<span style='font-size:1.1em'>{PLAYER_INFO[p]['emoji']}</span>"
                for p in PLAYER_INFO if cond in player_conds[p]
            )
            st.markdown(f"""
            <div class="condition-rung"
                 style="background:{color}18;border-left-color:{color}">
                <span style="color:{color}">{emoji} {cond.upper()}</span>
                <span>{markers}</span>
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown("**HOW XP IS EARNED**")
        st.markdown(f"""
| Action | XP |
|---|---|
| ✅ Complete a battle plan | +10 |
| 🎯 Complete a formula step | +15 |
| 📅 Daily check-in (per streak day) | +5 |
| 📊 Stat in Normal condition | +60 |
| 🚀 Stat in Affluence | +80 |
| 👑 Stat in Power | +100 |

**⚡ {PLAYER_INFO["Mareks"]["emoji"]} Mareks** = {get_player_xp("Mareks")} XP total
**🌸 {PLAYER_INFO["Karen"]["emoji"]} Karen** = {get_player_xp("Karen")} XP total
        """)
        st.caption("Emoji markers on the ladder show each player's current stat conditions. Higher = better. Work the formula steps in Battle Plans to move up!")


# ─────────────────────────────────────────────────────────────────────────────
# BATTLE PLANS TAB
# ─────────────────────────────────────────────────────────────────────────────
def _render_plans_for_player(player_name):
    pinfo  = PLAYER_INFO[player_name]
    streak = get_bp_streak(player_name)
    week   = this_monday()

    # Streak banner
    if streak >= 7:
        fires = "🔥" * 7
        st.markdown(f"""
        <div class="streak-box"
             style="background:{pinfo['bg']};border-color:{pinfo['color']}88">
            <span style="color:{pinfo['color']};font-size:1.15em;font-weight:bold">
                {fires} LEGENDARY STREAK — {streak} DAYS! {fires}
            </span>
        </div>
        """, unsafe_allow_html=True)
    elif streak >= 3:
        fires = "🔥" * min(streak, 7)
        st.markdown(f"""
        <div class="streak-box"
             style="background:{pinfo['bg']};border-color:{pinfo['color']}55">
            <span style="color:{pinfo['color']};font-weight:bold">
                {fires} PLAN STREAK: {streak} DAYS IN A ROW!
            </span>
        </div>
        """, unsafe_allow_html=True)
    elif streak > 0:
        st.markdown(f"""
        <div class="streak-box" style="background:#111120;border-color:#333">
            <span style="color:#aaa">
                🔥 Plan streak: <b style="color:{pinfo['color']}">{streak} day{"s" if streak != 1 else ""}</b>
                — keep going!
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="streak-box" style="background:#111120;border-color:#222;border-style:dashed">
            <span style="color:#444">Complete a plan today to start your streak! 💪</span>
        </div>
        """, unsafe_allow_html=True)

    # Add plan form
    with st.form(f"add_plan_{player_name}", clear_on_submit=True):
        c1, c2, c3 = st.columns([3.5, 1.5, 1])
        plan_text = c1.text_input(
            "Plan", placeholder="What's your battle plan for today?",
            label_visibility="collapsed"
        )
        plan_type = c2.selectbox(
            "Type", ["daily", "weekly", "monthly"],
            label_visibility="collapsed"
        )
        if c3.form_submit_button("➕ Add", use_container_width=True):
            if plan_text.strip():
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO battle_plans "
                        "(player_name, plan_text, plan_type, week_date, done, created_at) "
                        "VALUES (?,?,?,?,0,?)",
                        (player_name, plan_text.strip(), plan_type,
                         week, datetime.now().isoformat())
                    )
                st.rerun()

    # Plans list
    with get_db() as conn:
        plans = conn.execute(
            "SELECT * FROM battle_plans WHERE player_name=? AND week_date=? "
            "ORDER BY plan_type, done, created_at",
            (player_name, week)
        ).fetchall()

    type_colors = {"daily": "#7aa2f7", "weekly": "#c3a7ff", "monthly": "#FFD700"}
    current_type = None

    for plan in plans:
        if plan["plan_type"] != current_type:
            current_type = plan["plan_type"]
            tc = type_colors.get(current_type, "#888")
            st.markdown(
                f"<div class='type-header' style='color:{tc}'>"
                f"📋 {current_type.upper()} PLANS</div>",
                unsafe_allow_html=True
            )

        pc1, pc2 = st.columns([11, 1])
        new_done = pc1.checkbox(
            plan["plan_text"],
            value=bool(plan["done"]),
            key=f"plan_{plan['id']}"
        )
        if new_done != bool(plan["done"]):
            cd = today_str() if new_done else None
            with get_db() as conn:
                conn.execute(
                    "UPDATE battle_plans SET done=?, completed_date=? WHERE id=?",
                    (1 if new_done else 0, cd, plan["id"])
                )
            st.rerun()
        if pc2.button("×", key=f"del_{plan['id']}"):
            with get_db() as conn:
                conn.execute("DELETE FROM battle_plans WHERE id=?", (plan["id"],))
            st.rerun()

    if not plans:
        st.caption("No plans for this week. Add your first battle plan above!")

    # Condition formula tasks (auto-generated from Stats tab)
    with get_db() as conn:
        tasks = conn.execute(
            "SELECT * FROM condition_tasks WHERE player_name=? AND week_date=? "
            "ORDER BY condition_name, step_num",
            (player_name, week)
        ).fetchall()

    if tasks:
        st.markdown("---")
        st.markdown("**🎯 CONDITION FORMULA TASKS** *(auto-generated from your stats)*")

        cur_cond = None
        for task in tasks:
            if task["condition_name"] != cur_cond:
                cur_cond = task["condition_name"]
                color = CONDITION_COLOR[cur_cond]
                emoji = CONDITION_EMOJI[cur_cond]
                st.markdown(f"""
                <div class="condition-task-header"
                     style="background:{color}18;border-left-color:{color}">
                    <span style="color:{color}">{emoji} {cur_cond.upper()} FORMULA
                    — {task['stat_name']}</span>
                </div>
                """, unsafe_allow_html=True)

            new_done = st.checkbox(
                f"Step {task['step_num']}: {task['step_text']}",
                value=bool(task["done"]),
                key=f"ct_{task['id']}"
            )
            if new_done != bool(task["done"]):
                with get_db() as conn:
                    conn.execute(
                        "UPDATE condition_tasks SET done=? WHERE id=?",
                        (1 if new_done else 0, task["id"])
                    )
                st.rerun()

        # Completion banners
        with get_db() as conn:
            groups = conn.execute(
                "SELECT condition_name, stat_name, COUNT(*) as total, SUM(done) as done_count "
                "FROM condition_tasks WHERE player_name=? AND week_date=? "
                "GROUP BY condition_name, stat_name",
                (player_name, week)
            ).fetchall()
        for g in groups:
            if g["total"] > 0 and g["total"] == g["done_count"]:
                color = CONDITION_COLOR[g["condition_name"]]
                st.markdown(f"""
                <div class="formula-complete"
                     style="background:{color}33;border:1px solid {color}">
                    <span style="color:{color}">
                        🏆 {g['condition_name'].upper()} FORMULA COMPLETE for {g['stat_name']}!
                        +{len(CONDITION_FORMULA.get(g['condition_name'], []))*15} XP
                    </span>
                </div>
                """, unsafe_allow_html=True)


def tab_battle_plans():
    st.markdown("### ✅ Battle Plans")
    tab_m, tab_k = st.tabs(["⚡ Mareks", "🌸 Karen"])
    with tab_m:
        _render_plans_for_player("Mareks")
    with tab_k:
        _render_plans_for_player("Karen")


# ─────────────────────────────────────────────────────────────────────────────
# STATS TAB
# ─────────────────────────────────────────────────────────────────────────────
def _render_stats_for_player(player_name):
    with get_db() as conn:
        stat_rows = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()
    stat_map = {r["name"]: r["id"] for r in stat_rows}

    if not stat_map:
        st.warning("No stats defined yet. Add them in the ⚙️ Manage tab.")
        return

    with st.form(f"entry_form_{player_name}"):
        c1, c2, c3 = st.columns(3)
        stat_label = c1.selectbox("Stat", list(stat_map.keys()))
        week       = c2.text_input("Week (YYYY-MM-DD)", value=this_monday())
        value_str  = c3.text_input("Value", placeholder="e.g. 1500")
        submitted  = st.form_submit_button("💾 Save Entry", use_container_width=True)

    if submitted:
        try:
            value = float(value_str)
        except ValueError:
            st.error("Value must be a number.")
            return

        stat_id = stat_map[stat_label]

        with get_db() as conn:
            conn.execute(
                "INSERT INTO player_entries (player_name, stat_id, week_date, value) "
                "VALUES (?,?,?,?) ON CONFLICT(player_name, stat_id, week_date) "
                "DO UPDATE SET value=excluded.value",
                (player_name, stat_id, week, value)
            )
            prev_week = (
                datetime.strptime(week, "%Y-%m-%d") - timedelta(weeks=1)
            ).strftime("%Y-%m-%d")
            prev_row = conn.execute(
                "SELECT value FROM player_entries "
                "WHERE player_name=? AND stat_id=? AND week_date=?",
                (player_name, stat_id, prev_week)
            ).fetchone()
            prev_value = prev_row["value"] if prev_row else None

        condition = get_condition(prev_value, value)
        color     = CONDITION_COLOR[condition]
        emoji     = CONDITION_EMOJI[condition]

        st.markdown(f"""
        <div class="condition-banner"
             style="background:linear-gradient(135deg,{color}cc,{color}33)">
            {emoji} CONDITION: {condition.upper()}
        </div>
        """, unsafe_allow_html=True)

        if prev_value is not None and prev_value != 0:
            pct = (value - prev_value) / prev_value * 100
            st.caption(
                f"Week: {week}  |  Previous: {prev_value:.2f}  |  "
                f"Current: {value:.2f}  |  Change: {pct:+.1f}%"
            )
        else:
            st.caption(f"Week: {week}  |  Previous: —  |  Current: {value:.2f}")

        # Auto-generate condition formula tasks for this week
        steps = CONDITION_FORMULA.get(condition, [])
        if steps:
            with get_db() as conn:
                conn.execute(
                    "DELETE FROM condition_tasks "
                    "WHERE player_name=? AND stat_name=? AND week_date=?",
                    (player_name, stat_label, this_monday())
                )
                for i, step in enumerate(steps, 1):
                    conn.execute(
                        "INSERT INTO condition_tasks "
                        "(player_name, stat_name, condition_name, step_num, step_text, done, week_date) "
                        "VALUES (?,?,?,?,?,0,?)",
                        (player_name, stat_label, condition, i, step, this_monday())
                    )
            st.markdown(f"**Formula steps added to your Battle Plans:**")
            for i, step in enumerate(steps, 1):
                st.markdown(f"- **Step {i}:** {step}")
            st.info(f"✅ Go to Battle Plans tab to work through your **{condition}** formula!")

    # Current week overview
    st.markdown("---")
    st.markdown(f"**This Week's Stats**")
    stat_conds = get_player_stat_conditions(player_name)

    if stat_conds:
        cols = st.columns(min(len(stat_conds), 3))
        for i, (sname, val, cond) in enumerate(stat_conds):
            color = CONDITION_COLOR[cond]
            emoji = CONDITION_EMOJI[cond]
            with cols[i % 3]:
                st.markdown(f"""
                <div class="stat-mini-card"
                     style="background:{color}18;border-color:{color}33">
                    <div style="color:#999;font-size:0.78em">{sname}</div>
                    <div style="color:white;font-size:1.6em;font-weight:bold">{val:.0f}</div>
                    <div style="color:{color};font-size:0.82em;font-weight:bold">
                        {emoji} {cond}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.caption("No entries yet this week.")


def tab_stats():
    st.markdown("### 📊 Stats")
    tab_m, tab_k = st.tabs(["⚡ Mareks", "🌸 Karen"])
    with tab_m:
        _render_stats_for_player("Mareks")
    with tab_k:
        _render_stats_for_player("Karen")


# ─────────────────────────────────────────────────────────────────────────────
# 2D ADMIN SCALE TAB
# ─────────────────────────────────────────────────────────────────────────────
def tab_admin_scale_2d():
    st.markdown("### 📜 2D Admin Scale — Mareks & Karen")
    st.caption("Your personal and family administration scale. Every level is pre-filled — edit any section to keep it current.")

    with get_db() as conn:
        rows = conn.execute("SELECT level_name, content FROM admin_scale_2d").fetchall()
    scale_data = {r["level_name"]: r["content"] for r in rows}

    level_order = [name for name, _ in ADMIN_SCALE_2D_DEFAULTS]

    for level_name in level_order:
        color   = ADMIN_LEVEL_COLORS.get(level_name, "#888")
        emoji   = ADMIN_LEVEL_EMOJI.get(level_name, "📄")
        content = scale_data.get(level_name, "")
        expanded = level_name in ("Goal", "Purpose", "Ideal Scene")

        with st.expander(f"{emoji} {level_name.upper()}", expanded=expanded):
            edit_key = f"edit_2d_{level_name}"

            if st.session_state.get(edit_key):
                with st.form(f"form_2d_{level_name}"):
                    new_content = st.text_area(
                        "Edit", value=content, height=320,
                        label_visibility="collapsed"
                    )
                    sc1, sc2 = st.columns(2)
                    if sc1.form_submit_button("💾 Save", use_container_width=True):
                        with get_db() as conn:
                            conn.execute(
                                "INSERT OR REPLACE INTO admin_scale_2d (level_name, content) VALUES (?,?)",
                                (level_name, new_content)
                            )
                        st.session_state[edit_key] = False
                        st.rerun()
                    if sc2.form_submit_button("Cancel", use_container_width=True):
                        st.session_state[edit_key] = False
                        st.rerun()
            else:
                st.markdown(f"""
                <div class="admin-section" style="border-left-color:{color}">
                    <pre style="color:#ccc;font-family:inherit;white-space:pre-wrap;
                                font-size:0.87em;line-height:1.6;margin:0">{content or "— not yet defined —"}</pre>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"✏️ Edit", key=f"btn_edit_{level_name}"):
                    st.session_state[edit_key] = True
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# HISTORY TAB
# ─────────────────────────────────────────────────────────────────────────────
def _render_history_for_player(player_name):
    with get_db() as conn:
        stat_rows = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()
    stat_map = {r["name"]: r["id"] for r in stat_rows}

    if not stat_map:
        st.info("No stats yet.")
        return

    c1, c2 = st.columns([3, 1])
    stat_label = c1.selectbox("Select stat", list(stat_map.keys()), key=f"hist_{player_name}")
    load       = c2.button("Load", key=f"load_{player_name}", use_container_width=True)

    if load:
        stat_id = stat_map[stat_label]
        with get_db() as conn:
            rows = conn.execute(
                "SELECT week_date, value FROM player_entries "
                "WHERE player_name=? AND stat_id=? ORDER BY week_date",
                (player_name, stat_id)
            ).fetchall()

        if not rows:
            st.info("No entries found for this selection.")
            return

        data, prev = [], None
        for row in rows:
            curr  = row["value"]
            cond  = get_condition(prev, curr)
            color = CONDITION_COLOR[cond]
            emoji = CONDITION_EMOJI[cond]
            change = f"{((curr-prev)/prev*100):+.1f}%" if prev and prev != 0 else "—"
            data.append({
                "Week":      row["week_date"],
                "Value":     f"{curr:.2f}",
                "Previous":  f"{prev:.2f}" if prev else "—",
                "Change %":  change,
                "Condition": f"{emoji} {cond}",
            })
            prev = curr

        st.dataframe(data, use_container_width=True)

        try:
            import pandas as pd
            df = pd.DataFrame([{"Week": r["week_date"], "Value": r["value"]} for r in rows])
            st.line_chart(df.set_index("Week"))
        except ImportError:
            pass


def tab_history():
    st.markdown("### 📈 History")
    tab_m, tab_k = st.tabs(["⚡ Mareks", "🌸 Karen"])
    with tab_m:
        _render_history_for_player("Mareks")
    with tab_k:
        _render_history_for_player("Karen")


# ─────────────────────────────────────────────────────────────────────────────
# MANAGE TAB
# ─────────────────────────────────────────────────────────────────────────────
def tab_manage():
    st.markdown("### ⚙️ Manage")
    col_stats, col_goal = st.columns(2)

    with col_stats:
        st.markdown("**📊 Stats / Metrics**")
        st.caption("Stats are shared between both players.")

        with st.expander("💡 Suggested stats to track"):
            for s in [
                "Monthly Income (EUR)", "Daily Steps (Karen)",
                "Savings (EUR)", "Debt Remaining (EUR)",
                "Duolingo Streak (days)", "Books Pages Written",
                "Water Intake (liters)", "Languages at B1+",
            ]:
                st.markdown(f"• {s}")

        with st.form("add_stat_form", clear_on_submit=True):
            stat_name = st.text_input("Stat Name", placeholder="e.g. Monthly Income (EUR)")
            if st.form_submit_button("Add Stat"):
                if stat_name.strip():
                    with get_db() as conn:
                        try:
                            conn.execute("INSERT INTO stats (name) VALUES (?)", (stat_name.strip(),))
                        except Exception:
                            st.error("That stat already exists.")
                    st.rerun()

        with get_db() as conn:
            stat_rows = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()

        for stat in stat_rows:
            confirm_key = f"confirm_del_{stat['id']}"
            sc1, sc2 = st.columns([5, 1])
            sc1.write(stat["name"])
            if not st.session_state.get(confirm_key):
                if sc2.button("🗑️", key=f"del_stat_{stat['id']}"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                cd1, cd2 = st.columns(2)
                if cd1.button("Yes, delete", key=f"yes_del_{stat['id']}", type="primary"):
                    with get_db() as conn:
                        conn.execute("DELETE FROM player_entries WHERE stat_id=?", (stat["id"],))
                        conn.execute("DELETE FROM stats WHERE id=?", (stat["id"],))
                    del st.session_state[confirm_key]
                    st.rerun()
                if cd2.button("Cancel", key=f"no_del_{stat['id']}"):
                    del st.session_state[confirm_key]
                    st.rerun()

    with col_goal:
        st.markdown("**🏠 Shared Goal**")

        with get_db() as conn:
            goal = conn.execute("SELECT * FROM shared_goals LIMIT 1").fetchone()

        if goal:
            with st.form("edit_goal_form"):
                title   = st.text_input("Title", value=goal["title"])
                desc    = st.text_area("Description", value=goal["description"] or "", height=60)
                gc1, gc2 = st.columns(2)
                target  = gc1.number_input("Target (EUR)",          value=float(goal["target_amount"]),  step=1000.0)
                current = gc2.number_input("Current Savings (EUR)", value=float(goal["current_amount"]), step=100.0)
                if st.form_submit_button("💾 Update Goal", use_container_width=True):
                    with get_db() as conn:
                        conn.execute(
                            "UPDATE shared_goals SET title=?, description=?, "
                            "target_amount=?, current_amount=? WHERE id=?",
                            (title, desc, target, current, goal["id"])
                        )
                    st.success("Goal updated!")
                    st.rerun()

        st.markdown("---")
        st.markdown("**🗑️ Clear This Week's Data**")
        for pname in PLAYER_INFO:
            clear_key = f"confirm_clear_{pname}"
            if not st.session_state.get(clear_key):
                if st.button(f"Clear {pname}'s plans this week", key=f"clr_{pname}"):
                    st.session_state[clear_key] = True
                    st.rerun()
            else:
                cc1, cc2 = st.columns(2)
                if cc1.button(f"Yes, clear {pname}", key=f"yes_clr_{pname}", type="primary"):
                    week = this_monday()
                    with get_db() as conn:
                        conn.execute(
                            "DELETE FROM battle_plans WHERE player_name=? AND week_date=?",
                            (pname, week)
                        )
                        conn.execute(
                            "DELETE FROM condition_tasks WHERE player_name=? AND week_date=?",
                            (pname, week)
                        )
                    del st.session_state[clear_key]
                    st.rerun()
                if cc2.button("Cancel", key=f"no_clr_{pname}"):
                    del st.session_state[clear_key]
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# AI BATTLE CHECK (optional — needs ANTHROPIC_API_KEY)
# ─────────────────────────────────────────────────────────────────────────────
def run_ai_battle_check(player_name):
    if not ANTHROPIC_AVAILABLE:
        st.error("Run: pip install anthropic")
        return
    key = get_api_key()
    if not key:
        st.error("Set ANTHROPIC_API_KEY in environment or Streamlit secrets.")
        return

    week = this_monday()
    with get_db() as conn:
        plans  = conn.execute(
            "SELECT plan_text, plan_type, done FROM battle_plans WHERE player_name=? AND week_date=?",
            (player_name, week)
        ).fetchall()
        goal_row = conn.execute(
            "SELECT content FROM admin_scale_2d WHERE level_name='Goal'"
        ).fetchone()
        purpose_row = conn.execute(
            "SELECT content FROM admin_scale_2d WHERE level_name='Purpose'"
        ).fetchone()

    stat_conds = get_player_stat_conditions(player_name)
    cond_text  = "\n".join(f"{name}: {cond} ({val:.0f})" for name, val, cond in stat_conds) or "No stats."
    plans_text = "\n".join(
        f"[{p['plan_type'].upper()}] {'[DONE]' if p['done'] else '[TODO]'} {p['plan_text']}"
        for p in plans
    ) or "No plans this week."

    prompt = (
        f"Player: {player_name}\n\n"
        f"GOALS:\n{goal_row['content'] if goal_row else '—'}\n\n"
        f"PURPOSES:\n{purpose_row['content'] if purpose_row else '—'}\n\n"
        f"CURRENT CONDITIONS:\n{cond_text}\n\n"
        f"BATTLE PLANS THIS WEEK:\n{plans_text}\n\n"
        "Review these battle plans against the goals. Reply in exactly 3 bullet points:\n"
        "• ALIGNED: what is contributing to the goal\n"
        "• MISSING: what is not addressed\n"
        "• RECOMMENDATION: one specific action to add or change\n\n"
        "Be direct. Max 100 words total."
    )

    with st.spinner("AI is thinking…"):
        try:
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=350,
                messages=[{"role": "user", "content": prompt}]
            )
            st.info(msg.content[0].text)
        except Exception as e:
            st.error(f"AI error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────
def check_login():
    try:
        correct_password = st.secrets["APP_PASSWORD"]
    except Exception:
        correct_password = os.environ.get("APP_PASSWORD", "admin123")

    if st.session_state.get("logged_in"):
        return True

    inject_css()
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:40px 0 24px">
            <div style="font-size:3.2em">🎯</div>
            <div style="color:white;font-size:1.8em;font-weight:bold;margin:8px 0">
                MISSION CONTROL
            </div>
            <div style="margin:6px 0">
                <span style="color:#7aa2f7;font-size:1.1em">⚡ Mareks</span>
                <span style="color:#555"> &nbsp;&amp;&nbsp; </span>
                <span style="color:#f7a8d8;font-size:1.1em">🌸 Karen</span>
            </div>
            <div style="color:#333;font-size:0.82em;margin-top:6px">2D Admin — Personal Mission</div>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login_form"):
            password  = st.text_input("Password", type="password", placeholder="Enter password…")
            submitted = st.form_submit_button("Enter Mission Control", use_container_width=True)
            if submitted:
                if password == correct_password:
                    st.session_state["logged_in"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")

    return False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if not check_login():
        return

    init_db()
    inject_css()

    hc, lc = st.columns([9, 1])
    hc.markdown("""
    <div style="background:linear-gradient(135deg,#080810,#100820);padding:12px 20px;
                border-radius:10px;margin-bottom:8px;border:1px solid #ffffff08">
        <span style="color:white;font-size:1.3em;font-weight:bold">MISSION CONTROL</span>
        <span style="color:#222"> — </span>
        <span style="color:#7aa2f7">⚡ Mareks</span>
        <span style="color:#333"> &amp; </span>
        <span style="color:#f7a8d8">🌸 Karen</span>
        <span style="color:#2a2a4e;font-size:0.82em;margin-left:12px">2D ADMIN</span>
    </div>
    """, unsafe_allow_html=True)
    if lc.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    tabs = st.tabs([
        "🏠 Dashboard",
        "✅ Battle Plans",
        "📊 Stats",
        "📜 2D Admin Scale",
        "📈 History",
        "⚙️ Manage",
    ])

    with tabs[0]: tab_dashboard()
    with tabs[1]: tab_battle_plans()
    with tabs[2]: tab_stats()
    with tabs[3]: tab_admin_scale_2d()
    with tabs[4]: tab_history()
    with tabs[5]: tab_manage()


if __name__ == "__main__":
    main()
