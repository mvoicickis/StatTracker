import streamlit as st
import sqlite3
import os
from datetime import datetime, timedelta

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mission Control — Stat Tracker",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")

ADMIN_SCALE_LEVELS = [
    (1,  "Goal"),
    (2,  "Purpose"),
    (3,  "Policy"),
    (4,  "Plans"),
    (5,  "Programs"),
    (6,  "Projects"),
    (7,  "Orders"),
    (8,  "Ideal Scene"),
    (9,  "Statistics"),
    (10, "Valuable Final Products (VFPs)"),
]

CONDITION_COLOR = {
    "Affluence":     "#2ecc71",
    "Normal":        "#3498db",
    "Emergency":     "#f39c12",
    "Danger":        "#e74c3c",
    "Non-Existence": "#95a5a6",
}

CONDITION_FORMULA = {
    "Affluence": [
        "1. Bypass normal operating expenses for expansion.",
        "2. Invest heavily into what is really working.",
        "3. Economize on what is not producing.",
        "4. Prepare for possible affluence crash by boosting normal stats.",
    ],
    "Normal": [
        "1. Find out what you are doing RIGHT and do MORE of it.",
        "2. Maintain current production levels.",
        "3. Strengthen what is working.",
        "4. Do not change what is producing results.",
    ],
    "Emergency": [
        "1. Promote — get your product or service known.",
        "2. Change your operating basis (change what you are doing).",
        "3. Economize to survive the period.",
        "4. Now is NOT the time to stop — push through.",
    ],
    "Danger": [
        "1. Bypass normal routine by personal inspection.",
        "2. Handle the most obvious immediate threats.",
        "3. Assign cause of the danger condition and handle it.",
        "4. Reorganize your activities so the danger does not repeat.",
        "5. Assign Emergency condition to the area when danger is passed.",
    ],
    "Non-Existence": [
        "1. Find out what is needed and wanted.",
        "2. Do, produce, or provide it.",
        "3. Make yourself known to those who need you.",
        "4. Become part of the existing scene.",
        "5. Flourish and prosper — then assign Normal.",
    ],
}

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                post TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL,
                stat_id INTEGER NOT NULL,
                week_date TEXT NOT NULL,
                value REAL NOT NULL,
                FOREIGN KEY(staff_id) REFERENCES staff(id),
                FOREIGN KEY(stat_id) REFERENCES stats(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_scale (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level_order INTEGER NOT NULL UNIQUE,
                level_name TEXT NOT NULL,
                content TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS battle_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_text TEXT NOT NULL,
                plan_type TEXT NOT NULL,
                week_date TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_condition(prev, curr):
    if prev is None or prev == 0:
        return "Non-Existence"
    pct = ((curr - prev) / prev) * 100
    if pct > 20:
        return "Affluence"
    elif pct >= 0:
        return "Normal"
    elif pct >= -20:
        return "Emergency"
    elif pct < -20 and curr > 0:
        return "Danger"
    else:
        return "Non-Existence"

def this_monday():
    today = datetime.today()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def get_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY", "")

# ── CSS ───────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    .stApp { background-color: #1e1e2e; color: white; }
    .block-container { padding-top: 1rem; }
    .stat-card {
        border-radius: 8px;
        padding: 10px 14px;
        margin: 4px 0;
        color: white;
    }
    .scale-item {
        background: #22223a;
        border-radius: 6px;
        padding: 6px 10px;
        margin: 3px 0;
        font-size: 0.85em;
    }
    .condition-banner {
        border-radius: 8px;
        padding: 18px;
        text-align: center;
        color: white;
        font-size: 1.5em;
        font-weight: bold;
        margin: 12px 0;
    }
    .plan-type-header {
        color: #7aa2f7;
        font-weight: bold;
        font-size: 0.85em;
        margin-top: 10px;
    }
    h1, h2, h3, h4 { color: white !important; }
    label { color: #ccc !important; }
    .stTabs [data-baseweb="tab"] {
        background: #2a2a3e;
        color: white;
        border-radius: 6px 6px 0 0;
    }
    .stTabs [aria-selected="true"] {
        background: #3d3d5c !important;
        color: white !important;
    }
    .stTextInput input, .stSelectbox select {
        background: #2a2a3e !important;
        color: white !important;
    }
    .stDataFrame { background: #2a2a3e; }
    div[data-testid="stForm"] {
        background: #22223a;
        border-radius: 8px;
        padding: 12px;
        border: none;
    }
    </style>
    """, unsafe_allow_html=True)

# ── Admin Scale Editor ────────────────────────────────────────────────────────
def show_scale_editor():
    with st.expander("ADMIN SCALE EDITOR", expanded=True):
        with get_db() as conn:
            existing = {
                r["level_order"]: r["content"]
                for r in conn.execute("SELECT level_order, content FROM admin_scale").fetchall()
            }

        with st.form("admin_scale_form"):
            values = {}
            for order, name in ADMIN_SCALE_LEVELS:
                values[order] = st.text_input(
                    f"{order:02d}. {name}",
                    value=existing.get(order, ""),
                    key=f"scale_input_{order}"
                )

            c1, c2, c3 = st.columns(3)
            save_ai    = c1.form_submit_button("Save & Check Alignment (AI)")
            save_no_ai = c2.form_submit_button("Save Without AI Check")
            cancel     = c3.form_submit_button("Cancel")

            if save_ai or save_no_ai:
                with get_db() as conn:
                    for order, name in ADMIN_SCALE_LEVELS:
                        content = values[order].strip()
                        existing_row = conn.execute(
                            "SELECT id FROM admin_scale WHERE level_order=?", (order,)
                        ).fetchone()
                        if existing_row:
                            conn.execute("UPDATE admin_scale SET content=? WHERE level_order=?", (content, order))
                        else:
                            conn.execute("INSERT INTO admin_scale (level_order, level_name, content) VALUES (?,?,?)", (order, name, content))
                st.session_state["show_scale_editor"] = False
                if save_ai:
                    st.session_state["run_alignment_check"] = True
                st.rerun()

            if cancel:
                st.session_state["show_scale_editor"] = False
                st.rerun()

# ── AI ────────────────────────────────────────────────────────────────────────
def run_ai_battle_check():
    if not ANTHROPIC_AVAILABLE:
        st.error("anthropic not installed. Run: pip install anthropic")
        return
    key = get_api_key()
    if not key:
        st.error("Set ANTHROPIC_API_KEY in environment or Streamlit secrets.")
        return

    with get_db() as conn:
        scale_rows = conn.execute("SELECT level_name, content FROM admin_scale ORDER BY level_order").fetchall()
        week       = this_monday()
        plans      = conn.execute("SELECT plan_text, plan_type, done FROM battle_plans WHERE week_date=?", (week,)).fetchall()
        staff_rows = conn.execute("SELECT id, name FROM staff").fetchall()
        stat_rows  = conn.execute("SELECT id, name FROM stats").fetchall()

    conditions = []
    with get_db() as conn:
        for staff in staff_rows:
            for stat in stat_rows:
                rows = conn.execute(
                    "SELECT value FROM entries WHERE staff_id=? AND stat_id=? ORDER BY week_date DESC LIMIT 2",
                    (staff["id"], stat["id"])
                ).fetchall()
                if rows:
                    curr = rows[0]["value"]
                    prev = rows[1]["value"] if len(rows) > 1 else None
                    cond = get_condition(prev, curr)
                    conditions.append(f"{staff['name']} / {stat['name']}: {cond} ({curr:.0f})")

    scale_text = "\n".join(f"{r['level_name']}: {r['content']}" for r in scale_rows if r["content"]) or "Not yet defined."
    plans_text = "\n".join(f"[{p['plan_type'].upper()}] {'[DONE]' if p['done'] else '[TODO]'} {p['plan_text']}" for p in plans) or "No plans this week."
    cond_text  = "\n".join(conditions) or "No stat data yet."

    prompt = (
        "You are an admin tech advisor reviewing a team's weekly battle plans.\n\n"
        f"ADMIN SCALE:\n{scale_text}\n\n"
        f"CURRENT STATISTICS & CONDITIONS:\n{cond_text}\n\n"
        f"BATTLE PLANS THIS WEEK:\n{plans_text}\n\n"
        "Review the battle plans against the goal, purpose, and current conditions.\n"
        "Reply in exactly 3 bullet points:\n"
        "• ALIGNED: what is contributing to the goal\n"
        "• MISSING: what is not addressed (especially Danger / Emergency stats)\n"
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
            st.session_state["ai_result"] = msg.content[0].text
            st.session_state["run_battle_check"] = False
            st.rerun()
        except Exception as e:
            st.error(f"AI error: {e}")

def run_ai_alignment_check():
    if not ANTHROPIC_AVAILABLE:
        st.error("anthropic not installed. Run: pip install anthropic")
        return
    key = get_api_key()
    if not key:
        st.error("Set ANTHROPIC_API_KEY in environment or Streamlit secrets.")
        return

    with get_db() as conn:
        rows = conn.execute("SELECT level_order, level_name, content FROM admin_scale ORDER BY level_order").fetchall()

    scale_text = "\n".join(f"{r['level_order']:02d}. {r['level_name']}: {r['content']}" for r in rows) or "Admin scale is empty."

    prompt = (
        "You are an admin scale alignment checker.\n\n"
        f"ADMIN SCALE:\n{scale_text}\n\n"
        "Check if each level logically supports the level above it.\n"
        "Format your reply as:\n"
        "  ✓  Goal → Purpose:    <one-line verdict>\n"
        "  ⚠  Purpose → Policy:  <issue if any>\n"
        "... (all 9 pairs)\n\n"
        "End with one line:  OVERALL: aligned / needs work / incomplete\n\n"
        "Be specific. Max 160 words."
    )

    with st.spinner("Checking alignment…"):
        try:
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=450,
                messages=[{"role": "user", "content": prompt}]
            )
            st.session_state["ai_result"] = msg.content[0].text
            st.session_state["run_alignment_check"] = False
            st.rerun()
        except Exception as e:
            st.error(f"AI error: {e}")

# ── Big Board Tab ─────────────────────────────────────────────────────────────
def tab_bigboard():
    with get_db() as conn:
        goal_row    = conn.execute("SELECT content FROM admin_scale WHERE level_order=1").fetchone()
        purpose_row = conn.execute("SELECT content FROM admin_scale WHERE level_order=2").fetchone()

    goal    = goal_row["content"]    if goal_row    else ""
    purpose = purpose_row["content"] if purpose_row else ""

    st.markdown(f"""
    <div style="background:#0d0d1a;padding:14px 20px;border-radius:8px;margin-bottom:16px">
        <div style="color:#7aa2f7;font-size:1.1em;font-weight:bold">GOAL &nbsp;&nbsp; {goal or "— not set —"}</div>
        <div style="color:#888;font-size:0.9em;margin-top:4px">PURPOSE &nbsp;&nbsp; {purpose or "— not set —"}</div>
    </div>
    """, unsafe_allow_html=True)

    col_left, col_center, col_right = st.columns([1.2, 2, 1.5])

    # ── Admin Scale panel ──────────────────────────────────────────────────────
    with col_left:
        h1, h2 = st.columns([3, 1])
        h1.markdown("**ADMIN SCALE**")
        if h2.button("Edit", key="edit_scale_btn"):
            st.session_state["show_scale_editor"] = not st.session_state.get("show_scale_editor", False)

        with get_db() as conn:
            rows = conn.execute("SELECT level_order, level_name, content FROM admin_scale ORDER BY level_order").fetchall()
        level_map = {r["level_order"]: r for r in rows}

        for order, name in ADMIN_SCALE_LEVELS:
            row     = level_map.get(order)
            content = row["content"] if row else ""
            filled  = bool(content.strip())
            dot     = "🟢" if filled else "⚪"
            short   = (content[:28] + "…") if len(content) > 28 else content
            st.markdown(f"""
            <div class="scale-item">
                {dot} <b>{name}</b>
                <div style="color:#666;font-size:0.85em">{short}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Stats panel ────────────────────────────────────────────────────────────
    with col_center:
        st.markdown("**STATISTICS**")
        with get_db() as conn:
            staff_rows = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
            stat_rows  = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()

        if not staff_rows or not stat_rows:
            st.info("No data yet. Add staff and stats in the Manage tab, then enter values in Enter Stats.")
        else:
            with get_db() as conn:
                for staff in staff_rows:
                    cards = []
                    for stat in stat_rows:
                        entry_rows = conn.execute(
                            "SELECT value FROM entries WHERE staff_id=? AND stat_id=? ORDER BY week_date DESC LIMIT 2",
                            (staff["id"], stat["id"])
                        ).fetchall()
                        if not entry_rows:
                            continue
                        curr  = entry_rows[0]["value"]
                        prev  = entry_rows[1]["value"] if len(entry_rows) > 1 else None
                        cond  = get_condition(prev, curr)
                        color = CONDITION_COLOR[cond]
                        cards.append((stat["name"], curr, cond, color))

                    if not cards:
                        continue

                    st.markdown(
                        f"**{staff['name']}** &nbsp; <span style='color:#888;font-size:0.85em'>{staff['post']}</span>",
                        unsafe_allow_html=True
                    )
                    for i in range(0, len(cards), 2):
                        c1, c2 = st.columns(2)
                        for j, col in enumerate([c1, c2]):
                            if i + j < len(cards):
                                sname, curr, cond, color = cards[i + j]
                                col.markdown(f"""
                                <div class="stat-card" style="background:{color}">
                                    <div style="font-size:0.85em">{sname}</div>
                                    <div style="font-size:1.5em;font-weight:bold">{curr:.0f}</div>
                                    <div style="font-size:0.75em;font-weight:bold">{cond}</div>
                                </div>
                                """, unsafe_allow_html=True)

    # ── Battle Plans panel ─────────────────────────────────────────────────────
    with col_right:
        st.markdown("**BATTLE PLANS**")

        with st.form("add_plan_form", clear_on_submit=True):
            fc1, fc2, fc3 = st.columns([3, 1.5, 1])
            plan_text = fc1.text_input("Plan", placeholder="Add a plan…", label_visibility="collapsed")
            plan_type = fc2.selectbox("Type", ["daily", "weekly"], label_visibility="collapsed")
            add_plan  = fc3.form_submit_button("Add")
            if add_plan and plan_text.strip():
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO battle_plans (plan_text, plan_type, week_date, done, created_at) VALUES (?,?,?,0,?)",
                        (plan_text.strip(), plan_type, this_monday(), datetime.now().isoformat())
                    )
                st.rerun()

        week = this_monday()
        with get_db() as conn:
            plans = conn.execute(
                "SELECT * FROM battle_plans WHERE week_date=? ORDER BY plan_type, done, created_at",
                (week,)
            ).fetchall()

        current_type = None
        for plan in plans:
            if plan["plan_type"] != current_type:
                current_type = plan["plan_type"]
                st.markdown(f"<div class='plan-type-header'>{current_type.upper()}</div>", unsafe_allow_html=True)

            pc1, pc2 = st.columns([9, 1])
            new_done = pc1.checkbox(
                plan["plan_text"],
                value=bool(plan["done"]),
                key=f"plan_{plan['id']}"
            )
            if new_done != bool(plan["done"]):
                with get_db() as conn:
                    conn.execute("UPDATE battle_plans SET done=? WHERE id=?", (1 if new_done else 0, plan["id"]))
                st.rerun()
            if pc2.button("×", key=f"del_{plan['id']}"):
                with get_db() as conn:
                    conn.execute("DELETE FROM battle_plans WHERE id=?", (plan["id"],))
                st.rerun()

        if not plans:
            st.caption("No plans this week. Add one above.")

    # ── Scale editor (inline) ──────────────────────────────────────────────────
    if st.session_state.get("show_scale_editor"):
        show_scale_editor()

    # ── AI bar ─────────────────────────────────────────────────────────────────
    st.divider()
    ai_c1, ai_c2, ai_c3 = st.columns([1.3, 1.3, 5])
    if ai_c1.button("AI CHECK — Battle Plans", use_container_width=True):
        st.session_state["run_battle_check"] = True
    if ai_c2.button("Check Admin Scale", use_container_width=True):
        st.session_state["run_alignment_check"] = True

    if st.session_state.get("run_battle_check"):
        run_ai_battle_check()
    elif st.session_state.get("run_alignment_check"):
        run_ai_alignment_check()
    elif "ai_result" in st.session_state:
        st.info(st.session_state["ai_result"])
    else:
        st.caption("Press AI CHECK to analyse your battle plans against the goal.")

# ── Enter Stats Tab ───────────────────────────────────────────────────────────
def tab_enter_stats():
    st.markdown("### Enter Stats")

    with get_db() as conn:
        staff_rows = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
        stat_rows  = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()

    staff_map = {f"{r['name']} ({r['post']})": r['id'] for r in staff_rows}
    stat_map  = {r['name']: r['id'] for r in stat_rows}

    if not staff_map or not stat_map:
        st.warning("No staff or stats found. Go to the Manage tab to add them first.")
        return

    with st.form("entry_form"):
        c1, c2, c3, c4 = st.columns(4)
        staff_label = c1.selectbox("Staff Member", list(staff_map.keys()))
        stat_label  = c2.selectbox("Stat", list(stat_map.keys()))
        week        = c3.text_input("Week (YYYY-MM-DD)", value=this_monday())
        value_str   = c4.text_input("Value")
        submitted   = st.form_submit_button("Save Entry", use_container_width=True)

    if submitted:
        try:
            value = float(value_str)
        except ValueError:
            st.error("Value must be a number.")
            return
        try:
            datetime.strptime(week, "%Y-%m-%d")
        except ValueError:
            st.error("Week must be YYYY-MM-DD format.")
            return

        staff_id = staff_map[staff_label]
        stat_id  = stat_map[stat_label]

        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM entries WHERE staff_id=? AND stat_id=? AND week_date=?",
                (staff_id, stat_id, week)
            ).fetchone()
            if existing:
                conn.execute("UPDATE entries SET value=? WHERE id=?", (value, existing["id"]))
            else:
                conn.execute(
                    "INSERT INTO entries (staff_id, stat_id, week_date, value) VALUES (?,?,?,?)",
                    (staff_id, stat_id, week, value)
                )

            prev_week = (datetime.strptime(week, "%Y-%m-%d") - timedelta(weeks=1)).strftime("%Y-%m-%d")
            prev_row  = conn.execute(
                "SELECT value FROM entries WHERE staff_id=? AND stat_id=? AND week_date=?",
                (staff_id, stat_id, prev_week)
            ).fetchone()
            prev_value = prev_row["value"] if prev_row else None

        condition = get_condition(prev_value, value)
        color     = CONDITION_COLOR[condition]

        st.markdown(f"""
        <div class="condition-banner" style="background:{color}">
            CONDITION: {condition.upper()}
        </div>
        """, unsafe_allow_html=True)

        prev_text = f"{prev_value:.2f}" if prev_value is not None else "No previous data"
        st.caption(f"Week: {week}  |  Previous: {prev_text}  |  Current: {value:.2f}")

        st.markdown("**Formula to apply:**")
        for step in CONDITION_FORMULA[condition]:
            st.markdown(f"- {step}")

# ── History Tab ───────────────────────────────────────────────────────────────
def tab_history():
    st.markdown("### History")

    with get_db() as conn:
        staff_rows = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
        stat_rows  = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()

    staff_map = {f"{r['name']} ({r['post']})": r['id'] for r in staff_rows}
    stat_map  = {r['name']: r['id'] for r in stat_rows}

    if not staff_map or not stat_map:
        st.warning("No staff or stats found.")
        return

    c1, c2, c3 = st.columns([2, 2, 1])
    staff_label = c1.selectbox("Staff", list(staff_map.keys()))
    stat_label  = c2.selectbox("Stat", list(stat_map.keys()))
    load        = c3.button("Load", use_container_width=True)

    if load:
        staff_id = staff_map[staff_label]
        stat_id  = stat_map[stat_label]

        with get_db() as conn:
            rows = conn.execute(
                "SELECT week_date, value FROM entries WHERE staff_id=? AND stat_id=? ORDER BY week_date",
                (staff_id, stat_id)
            ).fetchall()

        if not rows:
            st.info("No entries found for this selection.")
            return

        data = []
        prev = None
        for row in rows:
            curr       = row["value"]
            cond       = get_condition(prev, curr)
            change_pct = f"{((curr - prev) / prev * 100):+.1f}%" if prev is not None and prev != 0 else "—"
            prev_disp  = f"{prev:.2f}" if prev is not None else "—"
            data.append({
                "Week":      row["week_date"],
                "Value":     f"{curr:.2f}",
                "Previous":  prev_disp,
                "Change %":  change_pct,
                "Condition": cond,
            })
            prev = curr

        st.dataframe(data, use_container_width=True)

        # Line chart
        try:
            import pandas as pd
            df = pd.DataFrame([{"Week": r["week_date"], "Value": r["value"]} for r in rows])
            st.line_chart(df.set_index("Week"))
        except ImportError:
            pass

# ── Manage Tab ────────────────────────────────────────────────────────────────
def tab_manage():
    st.markdown("### Manage")

    col_staff, col_stats = st.columns(2)

    with col_staff:
        st.markdown("**Staff Members**")
        with st.form("add_staff_form", clear_on_submit=True):
            sc1, sc2 = st.columns(2)
            staff_name = sc1.text_input("Name")
            staff_post = sc2.text_input("Post")
            if st.form_submit_button("Add Staff"):
                if staff_name.strip():
                    with get_db() as conn:
                        conn.execute("INSERT INTO staff (name, post) VALUES (?,?)", (staff_name.strip(), staff_post.strip()))
                    st.success(f"Added {staff_name}")
                    st.rerun()
                else:
                    st.warning("Enter a name.")

        with get_db() as conn:
            staff_rows = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()

        for staff in staff_rows:
            sc1, sc2 = st.columns([5, 1])
            sc1.write(f"{staff['name']} ({staff['post']})")
            if sc2.button("Delete", key=f"del_staff_{staff['id']}"):
                if st.session_state.get(f"confirm_staff_{staff['id']}"):
                    with get_db() as conn:
                        conn.execute("DELETE FROM entries WHERE staff_id=?", (staff["id"],))
                        conn.execute("DELETE FROM staff WHERE id=?", (staff["id"],))
                    st.rerun()
                else:
                    st.session_state[f"confirm_staff_{staff['id']}"] = True
                    st.warning(f"Click Delete again to confirm removing {staff['name']} and all their data.")

    with col_stats:
        st.markdown("**Stats / Metrics**")
        with st.form("add_stat_form", clear_on_submit=True):
            stat_name = st.text_input("Stat Name")
            if st.form_submit_button("Add Stat"):
                if stat_name.strip():
                    with get_db() as conn:
                        conn.execute("INSERT INTO stats (name) VALUES (?)", (stat_name.strip(),))
                    st.success(f"Added {stat_name}")
                    st.rerun()
                else:
                    st.warning("Enter a stat name.")

        with get_db() as conn:
            stat_rows = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()

        for stat in stat_rows:
            stc1, stc2 = st.columns([5, 1])
            stc1.write(stat["name"])
            if stc2.button("Delete", key=f"del_stat_{stat['id']}"):
                if st.session_state.get(f"confirm_stat_{stat['id']}"):
                    with get_db() as conn:
                        conn.execute("DELETE FROM entries WHERE stat_id=?", (stat["id"],))
                        conn.execute("DELETE FROM stats WHERE id=?", (stat["id"],))
                    st.rerun()
                else:
                    st.session_state[f"confirm_stat_{stat['id']}"] = True
                    st.warning(f"Click Delete again to confirm removing '{stat['name']}' and all its data.")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    inject_css()

    st.markdown("""
    <div style="background:#0d0d1a;padding:12px 20px;border-radius:8px;margin-bottom:8px">
        <span style="color:white;font-size:1.3em;font-weight:bold">MISSION CONTROL</span>
        <span style="color:#444;font-size:0.9em"> — Stat Tracker</span>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["  Big Board  ", "  Enter Stats  ", "  History  ", "  Manage  "])

    with tab1:
        tab_bigboard()
    with tab2:
        tab_enter_stats()
    with tab3:
        tab_history()
    with tab4:
        tab_manage()

if __name__ == "__main__":
    main()
