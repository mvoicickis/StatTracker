import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sqlite3
import os
from datetime import datetime, timedelta
import threading

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.expanduser("~"), "AppData", "Local", "StatTracker", "data.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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

# ── Condition logic ───────────────────────────────────────────────────────────
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

# ── Main App ──────────────────────────────────────────────────────────────────
class StatTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mission Control — Stat Tracker")
        self.geometry("1280x780")
        self.configure(bg="#1e1e2e")
        self.resizable(True, True)
        init_db()
        self._build_ui()
        self.after(400, self._check_admin_scale_setup)

    def _this_monday(self):
        today = datetime.today()
        monday = today - timedelta(days=today.weekday())
        return monday.strftime("%Y-%m-%d")

    # ── UI SHELL ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#0d0d1a", pady=9)
        top.pack(fill="x")
        tk.Label(top, text="  MISSION CONTROL",
                 font=("Segoe UI", 15, "bold"),
                 bg="#0d0d1a", fg="white").pack(side="left")
        tk.Label(top, text="Stat Tracker  ",
                 font=("Segoe UI", 9), bg="#0d0d1a", fg="#444").pack(side="right")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1e2e", borderwidth=0)
        style.configure("TNotebook.Tab", background="#2a2a3e", foreground="white",
                        padding=[14, 7], font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", "#3d3d5c")])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_board   = tk.Frame(nb, bg="#1e1e2e")
        self.tab_entry   = tk.Frame(nb, bg="#1e1e2e")
        self.tab_history = tk.Frame(nb, bg="#1e1e2e")
        self.tab_manage  = tk.Frame(nb, bg="#1e1e2e")

        nb.add(self.tab_board,   text="  Big Board  ")
        nb.add(self.tab_entry,   text="  Enter Stats  ")
        nb.add(self.tab_history, text="  History  ")
        nb.add(self.tab_manage,  text="  Manage  ")

        self._build_bigboard_tab()
        self._build_entry_tab()
        self._build_history_tab()
        self._build_manage_tab()

    # ── ADMIN SCALE WIZARD ────────────────────────────────────────────────────
    def _check_admin_scale_setup(self):
        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as c FROM admin_scale WHERE content != ''"
            ).fetchone()["c"]
        if count == 0:
            self._show_admin_scale_wizard()

    def _show_admin_scale_wizard(self, edit_mode=False):
        win = tk.Toplevel(self)
        win.title("Admin Scale — Mission Briefing")
        win.geometry("720x640")
        win.configure(bg="#1e1e2e")
        win.grab_set()

        tk.Label(win, text="ADMIN SCALE SETUP",
                 font=("Segoe UI", 16, "bold"),
                 bg="#1e1e2e", fg="white").pack(pady=(20, 4))
        tk.Label(win,
                 text="Define your mission from top to bottom. AI will verify alignment.",
                 font=("Segoe UI", 10), bg="#1e1e2e", fg="#888").pack(pady=(0, 14))

        # Scrollable form
        outer = tk.Frame(win, bg="#1e1e2e")
        outer.pack(fill="both", expand=True, padx=20)

        canvas = tk.Canvas(outer, bg="#1e1e2e", highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        form = tk.Frame(canvas, bg="#1e1e2e")

        form.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        with get_db() as conn:
            existing = {
                r["level_order"]: r["content"]
                for r in conn.execute("SELECT level_order, content FROM admin_scale").fetchall()
            }

        self._wizard_vars = {}
        for order, name in ADMIN_SCALE_LEVELS:
            row = tk.Frame(form, bg="#1e1e2e", pady=4)
            row.pack(fill="x")

            tk.Label(row, text=f"{order:02d}. {name}",
                     font=("Segoe UI", 10, "bold"),
                     bg="#1e1e2e", fg="#7aa2f7",
                     width=30, anchor="w").grid(row=0, column=0, sticky="w")

            var = tk.StringVar(value=existing.get(order, ""))
            tk.Entry(row, textvariable=var, width=44,
                     bg="#2a2a3e", fg="white",
                     insertbackground="white",
                     font=("Segoe UI", 10),
                     relief="flat").grid(row=0, column=1, padx=8)
            self._wizard_vars[order] = var

        # Buttons
        btn_row = tk.Frame(win, bg="#1e1e2e")
        btn_row.pack(pady=14)

        tk.Button(btn_row, text="Save & Check Alignment (AI)",
                  command=lambda: self._save_admin_scale(win, ai_check=True),
                  bg="#7aa2f7", fg="#1e1e2e", relief="flat", padx=16,
                  font=("Segoe UI", 11, "bold")).pack(side="left", padx=6)

        tk.Button(btn_row, text="Save Without AI Check",
                  command=lambda: self._save_admin_scale(win, ai_check=False),
                  bg="#3d3d5c", fg="white", relief="flat", padx=12).pack(side="left", padx=6)

        if edit_mode:
            tk.Button(btn_row, text="Cancel",
                      command=win.destroy,
                      bg="#3d3d5c", fg="white", relief="flat", padx=12).pack(side="left", padx=6)

    def _save_admin_scale(self, win, ai_check=True):
        with get_db() as conn:
            for order, name in ADMIN_SCALE_LEVELS:
                content = self._wizard_vars[order].get().strip()
                existing = conn.execute(
                    "SELECT id FROM admin_scale WHERE level_order=?", (order,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE admin_scale SET content=? WHERE level_order=?",
                        (content, order)
                    )
                else:
                    conn.execute(
                        "INSERT INTO admin_scale (level_order, level_name, content) VALUES (?,?,?)",
                        (order, name, content)
                    )
        win.destroy()
        self._refresh_bigboard()
        if ai_check:
            self._run_ai_alignment_check()

    # ── BIG BOARD TAB ─────────────────────────────────────────────────────────
    def _build_bigboard_tab(self):
        f = self.tab_board

        # Goal / Purpose banner
        self.banner_frame = tk.Frame(f, bg="#0d0d1a", pady=10, padx=16)
        self.banner_frame.pack(fill="x")
        self.banner_goal = tk.Label(
            self.banner_frame, text="GOAL: —",
            font=("Segoe UI", 12, "bold"),
            bg="#0d0d1a", fg="#7aa2f7", anchor="w")
        self.banner_goal.pack(anchor="w")
        self.banner_purpose = tk.Label(
            self.banner_frame, text="PURPOSE: —",
            font=("Segoe UI", 10),
            bg="#0d0d1a", fg="#888", anchor="w")
        self.banner_purpose.pack(anchor="w")

        # Three-column body
        body = tk.Frame(f, bg="#1e1e2e")
        body.pack(fill="both", expand=True, padx=8, pady=6)

        left   = tk.Frame(body, bg="#1e1e2e", width=230)
        center = tk.Frame(body, bg="#1e1e2e")
        right  = tk.Frame(body, bg="#1e1e2e", width=290)

        left.pack(side="left", fill="y", padx=(0, 6))
        center.pack(side="left", fill="both", expand=True, padx=6)
        right.pack(side="left", fill="y", padx=(6, 0))

        left.pack_propagate(False)
        right.pack_propagate(False)

        self._build_admin_scale_panel(left)
        self._build_stats_panel(center)
        self._build_battle_plans_panel(right)

        # AI bar (bottom)
        ai_bar = tk.Frame(f, bg="#0d0d1a", pady=8, padx=12)
        ai_bar.pack(fill="x", side="bottom")

        btns = tk.Frame(ai_bar, bg="#0d0d1a")
        btns.pack(side="left")

        tk.Button(btns, text="AI CHECK — Battle Plans",
                  command=self._run_ai_battle_check,
                  bg="#7aa2f7", fg="#1e1e2e", relief="flat", padx=14,
                  font=("Segoe UI", 10, "bold")).pack(side="left")

        tk.Button(btns, text="Check Admin Scale",
                  command=self._run_ai_alignment_check,
                  bg="#3d3d5c", fg="white", relief="flat", padx=10,
                  font=("Segoe UI", 9)).pack(side="left", padx=6)

        self.ai_result_label = tk.Label(
            ai_bar,
            text="Press  AI CHECK  to analyse your battle plans against the goal.",
            font=("Segoe UI", 9), bg="#0d0d1a", fg="#666",
            wraplength=860, justify="left")
        self.ai_result_label.pack(side="left", padx=14)

        self._refresh_bigboard()

    # ── Admin Scale panel ─────────────────────────────────────────────────────
    def _build_admin_scale_panel(self, parent):
        hdr = tk.Frame(parent, bg="#1e1e2e")
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(hdr, text="ADMIN SCALE",
                 font=("Segoe UI", 11, "bold"),
                 bg="#1e1e2e", fg="white").pack(side="left")
        tk.Button(hdr, text="Edit",
                  command=lambda: self._show_admin_scale_wizard(edit_mode=True),
                  bg="#3d3d5c", fg="white", relief="flat", padx=8).pack(side="right")

        self.scale_frame = tk.Frame(parent, bg="#1e1e2e")
        self.scale_frame.pack(fill="both", expand=True)

    def _refresh_admin_scale_panel(self):
        for w in self.scale_frame.winfo_children():
            w.destroy()

        with get_db() as conn:
            rows = conn.execute(
                "SELECT level_order, level_name, content FROM admin_scale ORDER BY level_order"
            ).fetchall()
        level_map = {r["level_order"]: r for r in rows}

        for order, name in ADMIN_SCALE_LEVELS:
            row   = level_map.get(order)
            content = row["content"] if row else ""
            filled  = bool(content.strip())

            item = tk.Frame(self.scale_frame, bg="#22223a", pady=5, padx=8)
            item.pack(fill="x", pady=2)

            status_color = "#2ecc71" if filled else "#444"
            tk.Label(item, text="●" if filled else "○",
                     font=("Segoe UI", 8),
                     bg="#22223a", fg=status_color, width=2).pack(side="left")

            tk.Label(item, text=name,
                     font=("Segoe UI", 9, "bold"),
                     bg="#22223a", fg="#ccc").pack(side="left", padx=4)

            if content:
                short = content[:28] + ("…" if len(content) > 28 else "")
                tk.Label(item, text=short,
                         font=("Segoe UI", 8),
                         bg="#22223a", fg="#666",
                         wraplength=170, justify="left").pack(anchor="w", padx=22)

    # ── Stats panel ──────────────────────────────────────────────────────────
    def _build_stats_panel(self, parent):
        hdr = tk.Frame(parent, bg="#1e1e2e")
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(hdr, text="STATISTICS",
                 font=("Segoe UI", 11, "bold"),
                 bg="#1e1e2e", fg="white").pack(side="left")
        tk.Button(hdr, text="Refresh",
                  command=self._refresh_stats_panel,
                  bg="#3d3d5c", fg="white", relief="flat", padx=8).pack(side="right")

        outer = tk.Frame(parent, bg="#1e1e2e")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg="#1e1e2e", highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.stats_inner = tk.Frame(canvas, bg="#1e1e2e")

        self.stats_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.stats_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._stats_canvas = canvas

    def _refresh_stats_panel(self):
        for w in self.stats_inner.winfo_children():
            w.destroy()

        with get_db() as conn:
            staff_rows = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
            stat_rows  = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()

        if not staff_rows or not stat_rows:
            tk.Label(self.stats_inner,
                     text="No data yet.\nAdd staff and stats in the Manage tab,\nthen enter values in Enter Stats.",
                     font=("Segoe UI", 10), bg="#1e1e2e", fg="#555",
                     justify="center").pack(pady=40)
            return

        with get_db() as conn:
            for staff in staff_rows:
                has_data = False
                cards = []

                for stat in stat_rows:
                    rows = conn.execute(
                        "SELECT value FROM entries "
                        "WHERE staff_id=? AND stat_id=? ORDER BY week_date DESC LIMIT 2",
                        (staff["id"], stat["id"])
                    ).fetchall()
                    if not rows:
                        continue
                    has_data = True
                    curr  = rows[0]["value"]
                    prev  = rows[1]["value"] if len(rows) > 1 else None
                    cond  = get_condition(prev, curr)
                    color = CONDITION_COLOR[cond]
                    cards.append((stat["name"], curr, cond, color))

                if not has_data:
                    continue

                # Staff header
                hdr = tk.Frame(self.stats_inner, bg="#1e1e2e")
                hdr.pack(fill="x", pady=(10, 2), padx=4)
                tk.Label(hdr,
                         text=f"{staff['name']}   {staff['post']}",
                         font=("Segoe UI", 10, "bold"),
                         bg="#1e1e2e", fg="white").pack(anchor="w")

                # Stat cards in a grid (2 per row)
                grid = tk.Frame(self.stats_inner, bg="#1e1e2e")
                grid.pack(fill="x", padx=4, pady=2)

                for i, (sname, curr, cond, color) in enumerate(cards):
                    col = i % 2
                    row_idx = i // 2

                    card = tk.Frame(grid, bg=color, padx=10, pady=8)
                    card.grid(row=row_idx, column=col, padx=3, pady=3, sticky="ew")
                    grid.columnconfigure(col, weight=1)

                    tk.Label(card, text=sname,
                             font=("Segoe UI", 9),
                             bg=color, fg="white").pack(anchor="w")
                    bottom = tk.Frame(card, bg=color)
                    bottom.pack(fill="x")
                    tk.Label(bottom, text=f"{curr:.0f}",
                             font=("Segoe UI", 15, "bold"),
                             bg=color, fg="white").pack(side="left")
                    tk.Label(bottom, text=cond,
                             font=("Segoe UI", 8, "bold"),
                             bg=color, fg="white").pack(side="right", anchor="s")

    # ── Battle Plans panel ────────────────────────────────────────────────────
    def _build_battle_plans_panel(self, parent):
        hdr = tk.Frame(parent, bg="#1e1e2e")
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(hdr, text="BATTLE PLANS",
                 font=("Segoe UI", 11, "bold"),
                 bg="#1e1e2e", fg="white").pack(side="left")

        # Input row
        add_frame = tk.Frame(parent, bg="#1e1e2e")
        add_frame.pack(fill="x", pady=(0, 8))

        self.plan_var  = tk.StringVar()
        self.plan_type = tk.StringVar(value="daily")

        entry = tk.Entry(add_frame, textvariable=self.plan_var,
                         bg="#2a2a3e", fg="white",
                         insertbackground="white",
                         font=("Segoe UI", 10), relief="flat", width=20)
        entry.pack(side="left", padx=(0, 4))
        entry.bind("<Return>", lambda e: self._add_battle_plan())

        ttk.Combobox(add_frame, textvariable=self.plan_type,
                     values=["daily", "weekly"],
                     state="readonly", width=7).pack(side="left", padx=2)

        tk.Button(add_frame, text="Add",
                  command=self._add_battle_plan,
                  bg="#2ecc71", fg="white", relief="flat", padx=8).pack(side="left", padx=4)

        # Scrollable list
        outer = tk.Frame(parent, bg="#1e1e2e")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg="#1e1e2e", highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.plans_inner = tk.Frame(canvas, bg="#1e1e2e")

        self.plans_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.plans_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _add_battle_plan(self):
        text = self.plan_var.get().strip()
        if not text:
            return
        with get_db() as conn:
            conn.execute(
                "INSERT INTO battle_plans (plan_text, plan_type, week_date, done, created_at) "
                "VALUES (?,?,?,0,?)",
                (text, self.plan_type.get(), self._this_monday(), datetime.now().isoformat())
            )
        self.plan_var.set("")
        self._refresh_battle_plans()

    def _toggle_battle_plan(self, plan_id, current_done):
        with get_db() as conn:
            conn.execute("UPDATE battle_plans SET done=? WHERE id=?",
                         (0 if current_done else 1, plan_id))
        self._refresh_battle_plans()

    def _delete_battle_plan(self, plan_id):
        with get_db() as conn:
            conn.execute("DELETE FROM battle_plans WHERE id=?", (plan_id,))
        self._refresh_battle_plans()

    def _refresh_battle_plans(self):
        for w in self.plans_inner.winfo_children():
            w.destroy()

        week = self._this_monday()
        with get_db() as conn:
            plans = conn.execute(
                "SELECT * FROM battle_plans WHERE week_date=? "
                "ORDER BY plan_type, done, created_at",
                (week,)
            ).fetchall()

        current_type = None
        for plan in plans:
            if plan["plan_type"] != current_type:
                current_type = plan["plan_type"]
                tk.Label(self.plans_inner,
                         text=current_type.upper(),
                         font=("Segoe UI", 9, "bold"),
                         bg="#1e1e2e", fg="#7aa2f7").pack(anchor="w", pady=(8, 2))

            row = tk.Frame(self.plans_inner, bg="#22223a", pady=4, padx=6)
            row.pack(fill="x", pady=1)

            var = tk.BooleanVar(value=bool(plan["done"]))
            tk.Checkbutton(row, variable=var,
                           bg="#22223a", activebackground="#22223a",
                           selectcolor="#3d3d5c",
                           command=lambda pid=plan["id"], d=plan["done"]: self._toggle_battle_plan(pid, d)
                           ).pack(side="left")

            fg    = "#555" if plan["done"] else "#ddd"
            font  = ("Segoe UI", 9, "overstrike") if plan["done"] else ("Segoe UI", 9)
            tk.Label(row, text=plan["plan_text"],
                     font=font, bg="#22223a", fg=fg,
                     anchor="w", wraplength=195, justify="left").pack(side="left", padx=4)

            tk.Button(row, text="×",
                      command=lambda pid=plan["id"]: self._delete_battle_plan(pid),
                      bg="#22223a", fg="#e74c3c", relief="flat",
                      font=("Segoe UI", 10, "bold")).pack(side="right")

        if not plans:
            tk.Label(self.plans_inner,
                     text="No plans this week.\nType one above and press Add.",
                     font=("Segoe UI", 9), bg="#1e1e2e", fg="#444",
                     justify="center").pack(pady=24)

    # ── Big Board refresh ─────────────────────────────────────────────────────
    def _refresh_bigboard(self):
        with get_db() as conn:
            goal_row    = conn.execute(
                "SELECT content FROM admin_scale WHERE level_order=1").fetchone()
            purpose_row = conn.execute(
                "SELECT content FROM admin_scale WHERE level_order=2").fetchone()

        goal    = goal_row["content"]    if goal_row    else ""
        purpose = purpose_row["content"] if purpose_row else ""

        self.banner_goal.config(   text=f"GOAL     {goal    or '— not set —'}")
        self.banner_purpose.config(text=f"PURPOSE  {purpose or '— not set —'}")

        self._refresh_admin_scale_panel()
        self._refresh_stats_panel()
        self._refresh_battle_plans()

    # ── AI ────────────────────────────────────────────────────────────────────
    def _get_api_key(self):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            messagebox.showinfo(
                "API Key Required",
                "Set the ANTHROPIC_API_KEY environment variable to use AI features.\n\n"
                "How to set it:\n"
                "  1. Open Windows Start → search 'environment variables'\n"
                "  2. Add:  ANTHROPIC_API_KEY = sk-ant-...\n"
                "  3. Restart the app\n\n"
                "Get a key at: console.anthropic.com"
            )
        return key

    def _run_ai_battle_check(self):
        if not ANTHROPIC_AVAILABLE:
            self.ai_result_label.config(
                text="anthropic package not installed. Run:  pip install anthropic",
                fg="#e74c3c")
            return

        key = self._get_api_key()
        if not key:
            return

        self.ai_result_label.config(text="Thinking…", fg="#888")

        with get_db() as conn:
            scale_rows = conn.execute(
                "SELECT level_name, content FROM admin_scale ORDER BY level_order"
            ).fetchall()
            week  = self._this_monday()
            plans = conn.execute(
                "SELECT plan_text, plan_type, done FROM battle_plans WHERE week_date=?",
                (week,)
            ).fetchall()
            staff_rows = conn.execute("SELECT id, name FROM staff").fetchall()
            stat_rows  = conn.execute("SELECT id, name FROM stats").fetchall()

        conditions = []
        with get_db() as conn:
            for staff in staff_rows:
                for stat in stat_rows:
                    rows = conn.execute(
                        "SELECT value FROM entries "
                        "WHERE staff_id=? AND stat_id=? ORDER BY week_date DESC LIMIT 2",
                        (staff["id"], stat["id"])
                    ).fetchall()
                    if rows:
                        curr  = rows[0]["value"]
                        prev  = rows[1]["value"] if len(rows) > 1 else None
                        cond  = get_condition(prev, curr)
                        conditions.append(f"{staff['name']} / {stat['name']}: {cond} ({curr:.0f})")

        scale_text = "\n".join(
            f"{r['level_name']}: {r['content']}"
            for r in scale_rows if r["content"]
        ) or "Not yet defined."

        plans_text = "\n".join(
            f"[{p['plan_type'].upper()}] {'[DONE]' if p['done'] else '[TODO]'} {p['plan_text']}"
            for p in plans
        ) or "No plans entered this week."

        cond_text = "\n".join(conditions) or "No stat data yet."

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

        def call_api():
            try:
                client = anthropic.Anthropic(api_key=key)
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=350,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = msg.content[0].text
                self.after(0, lambda: self.ai_result_label.config(
                    text=result, fg="#ccc"))
            except Exception as e:
                self.after(0, lambda: self.ai_result_label.config(
                    text=f"AI error: {e}", fg="#e74c3c"))

        threading.Thread(target=call_api, daemon=True).start()

    def _run_ai_alignment_check(self):
        if not ANTHROPIC_AVAILABLE:
            messagebox.showinfo("Missing Package",
                                "Run in terminal:  pip install anthropic")
            return

        key = self._get_api_key()
        if not key:
            return

        with get_db() as conn:
            rows = conn.execute(
                "SELECT level_order, level_name, content FROM admin_scale ORDER BY level_order"
            ).fetchall()

        scale_text = "\n".join(
            f"{r['level_order']:02d}. {r['level_name']}: {r['content']}"
            for r in rows
        ) or "Admin scale is empty."

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

        def call_api():
            try:
                client = anthropic.Anthropic(api_key=key)
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=450,
                    messages=[{"role": "user", "content": prompt}]
                )
                result = msg.content[0].text
                self.after(0, lambda: self._show_alignment_result(result))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("AI Error", str(e)))

        threading.Thread(target=call_api, daemon=True).start()

    def _show_alignment_result(self, result):
        win = tk.Toplevel(self)
        win.title("Admin Scale — Alignment Check")
        win.geometry("580x420")
        win.configure(bg="#1e1e2e")

        tk.Label(win, text="ALIGNMENT CHECK",
                 font=("Segoe UI", 13, "bold"),
                 bg="#1e1e2e", fg="white").pack(pady=(18, 8))

        text = scrolledtext.ScrolledText(
            win, bg="#22223a", fg="#ddd",
            font=("Segoe UI", 10),
            relief="flat", padx=14, pady=12)
        text.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        text.insert("end", result)
        text.config(state="disabled")

    # ── ENTER STATS TAB ───────────────────────────────────────────────────────
    def _build_entry_tab(self):
        f   = self.tab_entry
        pad = dict(padx=10, pady=6)

        row0 = tk.Frame(f, bg="#1e1e2e")
        row0.pack(fill="x", **pad)

        tk.Label(row0, text="Staff Member:", bg="#1e1e2e", fg="#ccc",
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.entry_staff_var = tk.StringVar()
        self.entry_staff_cb  = ttk.Combobox(row0, textvariable=self.entry_staff_var,
                                            width=25, state="readonly")
        self.entry_staff_cb.grid(row=0, column=1, padx=8)

        tk.Label(row0, text="Stat:", bg="#1e1e2e", fg="#ccc",
                 font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w")
        self.entry_stat_var = tk.StringVar()
        self.entry_stat_cb  = ttk.Combobox(row0, textvariable=self.entry_stat_var,
                                           width=25, state="readonly")
        self.entry_stat_cb.grid(row=0, column=3, padx=8)

        tk.Button(row0, text="Refresh Lists", command=self._refresh_entry_lists,
                  bg="#3d3d5c", fg="white", relief="flat", padx=8).grid(row=0, column=4, padx=8)

        row1 = tk.Frame(f, bg="#1e1e2e")
        row1.pack(fill="x", **pad)

        tk.Label(row1, text="Week (YYYY-MM-DD):", bg="#1e1e2e", fg="#ccc",
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.entry_week_var = tk.StringVar(value=self._this_monday())
        tk.Entry(row1, textvariable=self.entry_week_var, width=14,
                 bg="#2a2a3e", fg="white", insertbackground="white").grid(row=0, column=1, padx=8)

        tk.Label(row1, text="Value:", bg="#1e1e2e", fg="#ccc",
                 font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w")
        self.entry_value_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.entry_value_var, width=12,
                 bg="#2a2a3e", fg="white", insertbackground="white").grid(row=0, column=3, padx=8)

        tk.Button(row1, text="Save Entry", command=self._save_entry,
                  bg="#2ecc71", fg="white", relief="flat", padx=12,
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=4, padx=8)

        self.result_frame = tk.Frame(f, bg="#1e1e2e")
        self.result_frame.pack(fill="both", expand=True, **pad)
        self._refresh_entry_lists()

    def _refresh_entry_lists(self):
        with get_db() as conn:
            staff = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
            stats = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()
        self._staff_map = {f"{r['name']} ({r['post']})": r['id'] for r in staff}
        self._stat_map  = {r['name']: r['id'] for r in stats}
        self.entry_staff_cb["values"] = list(self._staff_map.keys())
        self.entry_stat_cb["values"]  = list(self._stat_map.keys())

    def _save_entry(self):
        staff_label = self.entry_staff_var.get()
        stat_label  = self.entry_stat_var.get()
        week        = self.entry_week_var.get().strip()
        value_str   = self.entry_value_var.get().strip()

        if not staff_label or not stat_label:
            messagebox.showwarning("Missing", "Please select staff and stat.")
            return
        try:
            value = float(value_str)
        except ValueError:
            messagebox.showwarning("Invalid", "Value must be a number.")
            return
        try:
            datetime.strptime(week, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Invalid", "Week must be YYYY-MM-DD.")
            return

        staff_id = self._staff_map[staff_label]
        stat_id  = self._stat_map[stat_label]

        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM entries WHERE staff_id=? AND stat_id=? AND week_date=?",
                (staff_id, stat_id, week)
            ).fetchone()
            if existing:
                conn.execute("UPDATE entries SET value=? WHERE id=?",
                             (value, existing["id"]))
            else:
                conn.execute(
                    "INSERT INTO entries (staff_id, stat_id, week_date, value) VALUES (?,?,?,?)",
                    (staff_id, stat_id, week, value)
                )

            prev_week = (
                datetime.strptime(week, "%Y-%m-%d") - timedelta(weeks=1)
            ).strftime("%Y-%m-%d")
            prev_row = conn.execute(
                "SELECT value FROM entries WHERE staff_id=? AND stat_id=? AND week_date=?",
                (staff_id, stat_id, prev_week)
            ).fetchone()
            prev_value = prev_row["value"] if prev_row else None

        condition = get_condition(prev_value, value)
        self._show_condition(condition, value, prev_value, week)
        self._refresh_stats_panel()

    def _show_condition(self, condition, curr, prev, week):
        for w in self.result_frame.winfo_children():
            w.destroy()

        color = CONDITION_COLOR[condition]

        header = tk.Frame(self.result_frame, bg=color, pady=10)
        header.pack(fill="x", pady=(10, 0))
        tk.Label(header, text=f"CONDITION:  {condition.upper()}",
                 font=("Segoe UI", 18, "bold"), bg=color, fg="white").pack()

        prev_text = f"{prev:.2f}" if prev is not None else "No previous data"
        tk.Label(self.result_frame,
                 text=f"Week: {week}    Previous: {prev_text}    Current: {curr:.2f}",
                 font=("Segoe UI", 10), bg="#1e1e2e", fg="#aaa").pack(pady=4)

        tk.Label(self.result_frame, text="Formula to apply:",
                 font=("Segoe UI", 11, "bold"),
                 bg="#1e1e2e", fg="white").pack(anchor="w", padx=10)

        steps_frame = tk.Frame(self.result_frame, bg="#2a2a3e", padx=15, pady=10)
        steps_frame.pack(fill="x", padx=10, pady=4)
        for step in CONDITION_FORMULA[condition]:
            tk.Label(steps_frame, text=step, font=("Segoe UI", 10),
                     bg="#2a2a3e", fg="#ddd",
                     justify="left", anchor="w",
                     wraplength=800).pack(anchor="w", pady=2)

    # ── HISTORY TAB ──────────────────────────────────────────────────────────
    def _build_history_tab(self):
        f   = self.tab_history
        pad = dict(padx=10, pady=6)

        ctrl = tk.Frame(f, bg="#1e1e2e")
        ctrl.pack(fill="x", **pad)

        tk.Label(ctrl, text="Staff:", bg="#1e1e2e", fg="#ccc",
                 font=("Segoe UI", 10)).grid(row=0, column=0)
        self.hist_staff_var = tk.StringVar()
        self.hist_staff_cb  = ttk.Combobox(ctrl, textvariable=self.hist_staff_var,
                                           width=25, state="readonly")
        self.hist_staff_cb.grid(row=0, column=1, padx=6)

        tk.Label(ctrl, text="Stat:", bg="#1e1e2e", fg="#ccc",
                 font=("Segoe UI", 10)).grid(row=0, column=2)
        self.hist_stat_var = tk.StringVar()
        self.hist_stat_cb  = ttk.Combobox(ctrl, textvariable=self.hist_stat_var,
                                          width=25, state="readonly")
        self.hist_stat_cb.grid(row=0, column=3, padx=6)

        tk.Button(ctrl, text="Load", command=self._load_history,
                  bg="#3498db", fg="white", relief="flat", padx=10).grid(row=0, column=4, padx=6)
        tk.Button(ctrl, text="Refresh Lists", command=self._refresh_history_lists,
                  bg="#3d3d5c", fg="white", relief="flat", padx=8).grid(row=0, column=5, padx=6)

        cols = ("Week", "Value", "Previous", "Change %", "Condition")
        style = ttk.Style()
        style.configure("Treeview", background="#2a2a3e", foreground="white",
                        fieldbackground="#2a2a3e", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#3d3d5c", foreground="white",
                        font=("Segoe UI", 10, "bold"))

        tree_frame = tk.Frame(f, bg="#1e1e2e")
        tree_frame.pack(fill="both", expand=True, **pad)

        self.hist_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        for c in cols:
            self.hist_tree.heading(c, text=c)
            self.hist_tree.column(c, width=150, anchor="center")
        self.hist_tree.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(tree_frame, orient="vertical",
                           command=self.hist_tree.yview)
        sb.pack(side="right", fill="y")
        self.hist_tree.configure(yscrollcommand=sb.set)

        self._refresh_history_lists()

    def _refresh_history_lists(self):
        with get_db() as conn:
            staff = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
            stats = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()
        self._hist_staff_map = {f"{r['name']} ({r['post']})": r['id'] for r in staff}
        self._hist_stat_map  = {r['name']: r['id'] for r in stats}
        self.hist_staff_cb["values"] = list(self._hist_staff_map.keys())
        self.hist_stat_cb["values"]  = list(self._hist_stat_map.keys())

    def _load_history(self):
        staff_label = self.hist_staff_var.get()
        stat_label  = self.hist_stat_var.get()
        if not staff_label or not stat_label:
            messagebox.showwarning("Missing", "Please select staff and stat.")
            return
        staff_id = self._hist_staff_map[staff_label]
        stat_id  = self._hist_stat_map[stat_label]

        with get_db() as conn:
            rows = conn.execute(
                "SELECT week_date, value FROM entries "
                "WHERE staff_id=? AND stat_id=? ORDER BY week_date",
                (staff_id, stat_id)
            ).fetchall()

        self.hist_tree.delete(*self.hist_tree.get_children())
        prev = None
        for row in rows:
            curr = row["value"]
            cond = get_condition(prev, curr)
            if prev is not None:
                change_pct = f"{((curr - prev) / prev * 100):+.1f}%" if prev != 0 else "N/A"
                prev_disp  = f"{prev:.2f}"
            else:
                change_pct = "—"
                prev_disp  = "—"
            color = CONDITION_COLOR[cond]
            tag   = cond.replace("-", "").replace(" ", "")
            self.hist_tree.tag_configure(tag, foreground=color)
            self.hist_tree.insert("", "end",
                values=(row["week_date"], f"{curr:.2f}", prev_disp, change_pct, cond),
                tags=(tag,))
            prev = curr

    # ── MANAGE TAB ───────────────────────────────────────────────────────────
    def _build_manage_tab(self):
        f = self.tab_manage

        left  = tk.Frame(f, bg="#1e1e2e", padx=10, pady=10)
        right = tk.Frame(f, bg="#1e1e2e", padx=10, pady=10)
        left.pack(side="left", fill="both", expand=True)
        right.pack(side="left", fill="both", expand=True)

        # Staff
        tk.Label(left, text="Staff Members",
                 font=("Segoe UI", 12, "bold"),
                 bg="#1e1e2e", fg="white").pack(anchor="w")

        inp = tk.Frame(left, bg="#1e1e2e")
        inp.pack(fill="x", pady=4)
        tk.Label(inp, text="Name:", bg="#1e1e2e", fg="#ccc").grid(row=0, column=0, sticky="w")
        self.staff_name_var = tk.StringVar()
        tk.Entry(inp, textvariable=self.staff_name_var, width=18,
                 bg="#2a2a3e", fg="white", insertbackground="white").grid(row=0, column=1, padx=4)
        tk.Label(inp, text="Post:", bg="#1e1e2e", fg="#ccc").grid(row=0, column=2, sticky="w")
        self.staff_post_var = tk.StringVar()
        tk.Entry(inp, textvariable=self.staff_post_var, width=18,
                 bg="#2a2a3e", fg="white", insertbackground="white").grid(row=0, column=3, padx=4)
        tk.Button(inp, text="Add", command=self._add_staff,
                  bg="#2ecc71", fg="white", relief="flat", padx=8).grid(row=0, column=4, padx=4)

        self.staff_list = tk.Listbox(left, bg="#2a2a3e", fg="white",
                                     selectbackground="#3d3d5c", height=15,
                                     font=("Segoe UI", 10))
        self.staff_list.pack(fill="both", expand=True, pady=4)
        tk.Button(left, text="Delete Selected Staff", command=self._delete_staff,
                  bg="#e74c3c", fg="white", relief="flat").pack(pady=2)

        # Stats
        tk.Label(right, text="Stats / Metrics",
                 font=("Segoe UI", 12, "bold"),
                 bg="#1e1e2e", fg="white").pack(anchor="w")

        inp2 = tk.Frame(right, bg="#1e1e2e")
        inp2.pack(fill="x", pady=4)
        tk.Label(inp2, text="Stat Name:", bg="#1e1e2e", fg="#ccc").grid(row=0, column=0, sticky="w")
        self.stat_name_var = tk.StringVar()
        tk.Entry(inp2, textvariable=self.stat_name_var, width=22,
                 bg="#2a2a3e", fg="white", insertbackground="white").grid(row=0, column=1, padx=4)
        tk.Button(inp2, text="Add", command=self._add_stat,
                  bg="#2ecc71", fg="white", relief="flat", padx=8).grid(row=0, column=2, padx=4)

        self.stat_list = tk.Listbox(right, bg="#2a2a3e", fg="white",
                                    selectbackground="#3d3d5c", height=15,
                                    font=("Segoe UI", 10))
        self.stat_list.pack(fill="both", expand=True, pady=4)
        tk.Button(right, text="Delete Selected Stat", command=self._delete_stat,
                  bg="#e74c3c", fg="white", relief="flat").pack(pady=2)

        self._refresh_manage_lists()

    def _refresh_manage_lists(self):
        with get_db() as conn:
            staff = conn.execute("SELECT id, name, post FROM staff ORDER BY name").fetchall()
            stats = conn.execute("SELECT id, name FROM stats ORDER BY name").fetchall()
        self._manage_staff = {f"{r['name']} ({r['post']})": r['id'] for r in staff}
        self._manage_stats  = {r['name']: r['id'] for r in stats}
        self.staff_list.delete(0, "end")
        for s in self._manage_staff:
            self.staff_list.insert("end", s)
        self.stat_list.delete(0, "end")
        for s in self._manage_stats:
            self.stat_list.insert("end", s)

    def _add_staff(self):
        name = self.staff_name_var.get().strip()
        post = self.staff_post_var.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Enter a staff name.")
            return
        with get_db() as conn:
            conn.execute("INSERT INTO staff (name, post) VALUES (?, ?)", (name, post))
        self.staff_name_var.set("")
        self.staff_post_var.set("")
        self._refresh_manage_lists()

    def _delete_staff(self):
        sel = self.staff_list.curselection()
        if not sel:
            return
        label = self.staff_list.get(sel[0])
        sid   = self._manage_staff[label]
        if messagebox.askyesno("Confirm", f"Delete {label} and all their entries?"):
            with get_db() as conn:
                conn.execute("DELETE FROM entries WHERE staff_id=?", (sid,))
                conn.execute("DELETE FROM staff WHERE id=?", (sid,))
            self._refresh_manage_lists()

    def _add_stat(self):
        name = self.stat_name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Enter a stat name.")
            return
        with get_db() as conn:
            conn.execute("INSERT INTO stats (name) VALUES (?)", (name,))
        self.stat_name_var.set("")
        self._refresh_manage_lists()

    def _delete_stat(self):
        sel = self.stat_list.curselection()
        if not sel:
            return
        name = self.stat_list.get(sel[0])
        sid  = self._manage_stats[name]
        if messagebox.askyesno("Confirm", f"Delete stat '{name}' and all its entries?"):
            with get_db() as conn:
                conn.execute("DELETE FROM entries WHERE stat_id=?", (sid,))
                conn.execute("DELETE FROM stats WHERE id=?", (sid,))
            self._refresh_manage_lists()


if __name__ == "__main__":
    app = StatTrackerApp()
    app.mainloop()
