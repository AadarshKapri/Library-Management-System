import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import datetime
import csv


try:
    import ttkbootstrap as ttkb
    HAS_BOOTSTRAP = True
except ImportError:
    HAS_BOOTSTRAP = False


DB_PATH       = "LBMS.db"
FINE_PER_DAY  = 2.0         
APP_TITLE     = "📚 Library Management System"
APP_GEOMETRY  = "1260x780"



class DatabaseManager:
    

    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._migrate_old_schema()
        self._initialize()

  
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


    def _migrate_old_schema(self) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(books)")
            cols = [r[1] for r in cur.fetchall()]
            if "lender_name" in cols:           
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS books_v2 (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        title           TEXT    NOT NULL,
                        author          TEXT    DEFAULT 'Unknown',
                        genre           TEXT    DEFAULT 'General',
                        isbn            TEXT,
                        total_copies    INTEGER DEFAULT 1,
                        available_copies INTEGER DEFAULT 1,
                        added_date      TEXT    DEFAULT CURRENT_TIMESTAMP
                    )""")
             
                cur.execute("""
                    INSERT INTO books_v2 (id, title,
                        total_copies, available_copies)
                    SELECT id, title,
                        1,
                        CASE WHEN status='Available' THEN 1 ELSE 0 END
                    FROM books
                """)
                cur.execute("DROP TABLE books")
                cur.execute("ALTER TABLE books_v2 RENAME TO books")
                conn.commit()


    def _initialize(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS books (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    title            TEXT    NOT NULL,
                    author           TEXT    DEFAULT 'Unknown',
                    genre            TEXT    DEFAULT 'General',
                    isbn             TEXT,
                    total_copies     INTEGER DEFAULT 1,
                    available_copies INTEGER DEFAULT 1,
                    added_date       TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS members (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    name      TEXT NOT NULL,
                    email     TEXT,
                    phone     TEXT,
                    join_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    active    INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id     INTEGER REFERENCES books(id),
                    member_id   INTEGER REFERENCES members(id),
                    issue_date  TEXT,
                    due_date    TEXT,
                    return_date TEXT,
                    fine_amount REAL    DEFAULT 0,
                    status      TEXT    DEFAULT 'Active'
                );
            """)


    def add_book(self, title, author, genre, isbn, copies) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO books (title, author, genre, isbn,
                                   total_copies, available_copies)
                VALUES (?,?,?,?,?,?)
            """, (title, author, genre, isbn, copies, copies))
            return cur.lastrowid

    def get_books(self, search: str = ""):
        with self._conn() as conn:
            like = f"%{search}%"
            if search:
                return conn.execute("""
                    SELECT id, title, author, genre, isbn,
                           total_copies, available_copies, added_date
                    FROM books
                    WHERE title LIKE ? OR author LIKE ? OR genre LIKE ? OR isbn LIKE ?
                    ORDER BY id DESC
                """, (like, like, like, like)).fetchall()
            return conn.execute("""
                SELECT id, title, author, genre, isbn,
                       total_copies, available_copies, added_date
                FROM books ORDER BY id DESC
            """).fetchall()

    def delete_book(self, book_id):
        with self._conn() as conn:
            active = conn.execute("""
                SELECT COUNT(*) FROM transactions
                WHERE book_id=? AND status='Active'
            """, (book_id,)).fetchone()[0]
            if active:
                return False, "Cannot delete — book has active issues."
            conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        return True, "Book deleted."


    def add_member(self, name, email, phone) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO members (name, email, phone) VALUES (?,?,?)",
                (name, email, phone))
            return cur.lastrowid

    def get_members(self, search: str = ""):
        with self._conn() as conn:
            like = f"%{search}%"
            if search:
                return conn.execute("""
                    SELECT id, name, email, phone, join_date
                    FROM members WHERE active=1
                    AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)
                    ORDER BY id DESC
                """, (like, like, like)).fetchall()
            return conn.execute("""
                SELECT id, name, email, phone, join_date
                FROM members WHERE active=1 ORDER BY id DESC
            """).fetchall()


    def issue_book(self, book_id, member_id, days: int):
        with self._conn() as conn:
            avail = conn.execute(
                "SELECT available_copies FROM books WHERE id=?", (book_id,)
            ).fetchone()
            if not avail or avail[0] < 1:
                return False, "Book not available."
            now      = datetime.datetime.now()
            due      = (now + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            issue_ts = now.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO transactions
                    (book_id, member_id, issue_date, due_date, status)
                VALUES (?,?,?,?,'Active')
            """, (book_id, member_id, issue_ts, due))
            conn.execute("""
                UPDATE books SET available_copies = available_copies - 1
                WHERE id=?
            """, (book_id,))
        return True, f"Issued! Due date: {due}"

    def return_book(self, transaction_id):
        with self._conn() as conn:
            row = conn.execute("""
                SELECT book_id, due_date FROM transactions
                WHERE id=? AND status='Active'
            """, (transaction_id,)).fetchone()
            if not row:
                return False, "Transaction not found or already returned.", 0
            book_id, due_date = row
            now  = datetime.datetime.now()
            due  = datetime.datetime.strptime(due_date, "%Y-%m-%d")
            fine = max(0, (now.date() - due.date()).days) * FINE_PER_DAY
            conn.execute("""
                UPDATE transactions
                SET return_date=?, fine_amount=?, status='Returned'
                WHERE id=?
            """, (now.strftime("%Y-%m-%d %H:%M:%S"), fine, transaction_id))
            conn.execute("""
                UPDATE books SET available_copies = available_copies + 1
                WHERE id=?
            """, (book_id,))
        return True, "Returned.", fine

    def get_transactions(self, status_filter=None, search=""):
        with self._conn() as conn:
            q   = """
                SELECT t.id, b.title, m.name,
                       t.issue_date, t.due_date, t.return_date,
                       t.fine_amount, t.status
                FROM transactions t
                JOIN books   b ON t.book_id   = b.id
                JOIN members m ON t.member_id = m.id
            """
            cond, params = [], []
            if status_filter:
                cond.append("t.status=?"); params.append(status_filter)
            if search:
                cond.append("(b.title LIKE ? OR m.name LIKE ?)")
                params += [f"%{search}%", f"%{search}%"]
            if cond:
                q += " WHERE " + " AND ".join(cond)
            q += " ORDER BY t.id DESC"
            return conn.execute(q, params).fetchall()

    def get_stats(self) -> dict:
        with self._conn() as conn:
            def scalar(sql, *p):
                r = conn.execute(sql, p).fetchone()[0]
                return r if r is not None else 0
            return {
                "total_books" : scalar("SELECT COUNT(*) FROM books"),
                "available"   : scalar("SELECT COALESCE(SUM(available_copies),0) FROM books"),
                "issued"      : scalar("SELECT COUNT(*) FROM transactions WHERE status='Active'"),
                "overdue"     : scalar("""
                    SELECT COUNT(*) FROM transactions
                    WHERE status='Active' AND due_date < DATE('now')"""),
                "members"     : scalar("SELECT COUNT(*) FROM members WHERE active=1"),
                "total_fines" : scalar(
                    "SELECT COALESCE(SUM(fine_amount),0) FROM transactions"),
            }


COLORS = {
    "header_bg"  : "#1a1a2e",
    "primary"    : "#3498db",
    "success"    : "#27ae60",
    "warning"    : "#e67e22",
    "danger"     : "#e74c3c",
    "purple"     : "#9b59b6",
    "teal"       : "#1abc9c",
    "panel_bg"   : "#f4f6f9",
    "card_border": "#dee2e6",
    "text_dark"  : "#2c3e50",
    "text_muted" : "#6c757d",
    "white"      : "#ffffff",
}

STAT_META = [
    ("total_books" , "#3498db", "#ebf5fb", "📚", "Total Books"    ),
    ("available"   , "#27ae60", "#eafaf1", "✅", "Available"      ),
    ("issued"      , "#e67e22", "#fef9e7", "📤", "Issued"         ),
    ("overdue"     , "#e74c3c", "#fdedec", "⚠️", "Overdue"        ),
    ("members"     , "#9b59b6", "#f5eef8", "👥", "Members"        ),
    ("total_fines" , "#1abc9c", "#e8f8f5", "₹",  "Total Fines"   ),
]


def styled_button(parent, text, command, color, **kwargs):
    btn = tk.Button(parent, text=text, command=command,
                    bg=color, fg=COLORS["white"],
                    font=("Segoe UI", 10, "bold"),
                    relief="flat", cursor="hand2",
                    activebackground=color, activeforeground=COLORS["white"],
                    **kwargs)
    btn.bind("<Enter>", lambda e: btn.config(bg=_darken(color)))
    btn.bind("<Leave>", lambda e: btn.config(bg=color))
    return btn


def _darken(hex_color: str) -> str:
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    r, g, b = max(0, r - 25), max(0, g - 25), max(0, b - 25)
    return f"#{r:02x}{g:02x}{b:02x}"


def labeled_entry(parent, label: str, bg: str = COLORS["panel_bg"], width=None):
    tk.Label(parent, text=label, bg=bg,
             font=("Segoe UI", 10), anchor="w",
             fg=COLORS["text_dark"]).pack(fill="x", padx=20)
    kw = dict(font=("Segoe UI", 10), relief="solid", bd=1)
    if width:
        kw["width"] = width
    e = tk.Entry(parent, **kw)
    e.pack(fill="x", padx=20, pady=(2, 10), ipady=5)
    return e


def side_panel(parent, title: str, width: int = 300):
    f = tk.Frame(parent, width=width, bg=COLORS["panel_bg"],
                 relief="solid", bd=1)
    f.pack(side="left", fill="y", padx=(10, 5), pady=10)
    f.pack_propagate(False)
    tk.Label(f, text=title, bg=COLORS["panel_bg"],
             font=("Segoe UI", 14, "bold"),
             fg=COLORS["text_dark"]).pack(pady=(20, 15))
    return f


def make_treeview(parent, cols: tuple, widths: dict, height: int = 20):
    frame = tk.Frame(parent)
    frame.pack(fill="both", expand=True)

    style = ttk.Style()
    style.configure("Treeview", font=("Segoe UI", 10), rowheight=26)
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    tree = ttk.Treeview(frame, columns=cols, show="headings", height=height)
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, width=widths.get(col, 120), anchor="center")

    sy = ttk.Scrollbar(frame, orient="vertical",   command=tree.yview)
    sx = ttk.Scrollbar(frame, orient="horizontal",  command=tree.xview)
    tree.configure(yscroll=sy.set, xscroll=sx.set)
    tree.pack(side="left", fill="both", expand=True)
    sy.pack(side="right", fill="y")
    sx.pack(side="bottom", fill="x")

    tree.tag_configure("overdue",   foreground="#e74c3c", font=("Segoe UI", 10, "bold"))
    tree.tag_configure("active",    foreground="#e67e22")
    tree.tag_configure("returned",  foreground="#27ae60")
    tree.tag_configure("unavail",   foreground="#e74c3c")
    tree.tag_configure("avail",     foreground="#27ae60")
    return tree


def divider(parent, bg):
    tk.Frame(parent, bg="#cccccc", height=1).pack(fill="x", padx=20, pady=8)



class LibraryApp:

    def __init__(self) -> None:
        self.db = DatabaseManager(DB_PATH)

        # ── root window ───────────────────────────────────────────────────────
        if HAS_BOOTSTRAP:
            self.root = ttkb.Window(themename="litera")
        else:
            self.root = tk.Tk()
            ttk.Style().theme_use("clam")

        self.root.title(APP_TITLE)
        self.root.geometry(APP_GEOMETRY)
        self.root.minsize(1050, 680)

        self._build_header()
        self._build_notebook()
        self._refresh_all()


    def _build_header(self):
        hdr = tk.Frame(self.root, bg=COLORS["header_bg"], height=58)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text=APP_TITLE,
                 bg=COLORS["header_bg"], fg=COLORS["white"],
                 font=("Segoe UI", 17, "bold")).pack(side="left", padx=22, pady=10)

        today_str = datetime.date.today().strftime("%A, %d %B %Y")
        tk.Label(hdr, text=today_str,
                 bg=COLORS["header_bg"], fg="#bdc3c7",
                 font=("Segoe UI", 11)).pack(side="right", padx=22)

   
    def _build_notebook(self):
        if HAS_BOOTSTRAP:
            self.nb = ttkb.Notebook(self.root, bootstyle="primary")
        else:
            self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_dashboard_tab()
        self._build_books_tab()
        self._build_members_tab()
        self._build_transactions_tab()


    def _build_dashboard_tab(self):
        self._dash = ttk.Frame(self.nb)
        self.nb.add(self._dash, text="  📊 Dashboard  ")

        tk.Label(self._dash, text="Library Overview",
                 font=("Segoe UI", 17, "bold"),
                 fg=COLORS["text_dark"]).pack(pady=(22, 2))
        tk.Label(self._dash, text="Real-time statistics",
                 font=("Segoe UI", 10), fg=COLORS["text_muted"]).pack()

     
        cards_row = tk.Frame(self._dash)
        cards_row.pack(fill="x", padx=30, pady=18)
        self._stat_vals: dict[str, tk.Label] = {}

        for i, (key, color, bg, icon, title) in enumerate(STAT_META):
            card = tk.Frame(cards_row, bg=bg,
                            relief="solid", bd=1, padx=10, pady=10)
            card.grid(row=0, column=i, padx=8, sticky="nsew")
            cards_row.grid_columnconfigure(i, weight=1)

            tk.Label(card, text=icon, bg=bg, font=("Segoe UI", 20)).pack(pady=(8, 3))
            val_lbl = tk.Label(card, text="—", bg=bg,
                               font=("Segoe UI", 26, "bold"), fg=color)
            val_lbl.pack()
            tk.Label(card, text=title, bg=bg,
                     font=("Segoe UI", 9), fg=COLORS["text_muted"]).pack(pady=(3, 10))
            self._stat_vals[key] = val_lbl

        tk.Label(self._dash, text="Recent Transactions",
                 font=("Segoe UI", 13, "bold"),
                 fg=COLORS["text_dark"]).pack(anchor="w", padx=32, pady=(6, 4))

        recent_wrap = tk.Frame(self._dash)
        recent_wrap.pack(fill="both", expand=True, padx=30, pady=(0, 16))

        self._recent_tree = make_treeview(
            recent_wrap,
            cols=("ID", "Book", "Member", "Issue Date", "Due Date", "Status"),
            widths={"ID": 55, "Book": 260, "Member": 190,
                    "Issue Date": 145, "Due Date": 100, "Status": 100},
            height=9,
        )


    def _build_books_tab(self):
        frame = ttk.Frame(self.nb)
        self.nb.add(frame, text="  📖 Books  ")

        # ── left panel ────────────────────────────────────────────────────────
        left = side_panel(frame, "Add New Book")

        self._b_entries = {
            "title" : labeled_entry(left, "Title  *"),
            "author": labeled_entry(left, "Author"),
            "genre" : labeled_entry(left, "Genre"),
            "isbn"  : labeled_entry(left, "ISBN"),
        }

        tk.Label(left, text="Copies", bg=COLORS["panel_bg"],
                 font=("Segoe UI", 10), anchor="w",
                 fg=COLORS["text_dark"]).pack(fill="x", padx=20)
        self._b_copies = tk.Spinbox(left, from_=1, to=500,
                                    font=("Segoe UI", 10))
        self._b_copies.pack(fill="x", padx=20, pady=(2, 14), ipady=5)

        styled_button(left, "➕  Add Book",   self._add_book,
                      COLORS["primary"], pady=8).pack(fill="x", padx=20, pady=4)
        styled_button(left, "🗑️  Delete Selected", self._delete_book,
                      COLORS["danger"],  pady=8).pack(fill="x", padx=20, pady=4)


        right = tk.Frame(frame)
        right.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=10)

        # search bar + export
        bar = tk.Frame(right)
        bar.pack(fill="x", pady=(0, 8))
        tk.Label(bar, text="🔍  Search:", font=("Segoe UI", 11)).pack(side="left")
        self._b_search = tk.StringVar()
        self._b_search.trace_add("write", lambda *_: self._refresh_books())
        tk.Entry(bar, textvariable=self._b_search,
                 font=("Segoe UI", 11), width=32,
                 relief="solid", bd=1).pack(side="left", padx=8, ipady=4)
        styled_button(bar, "📥 Export CSV", self._export_books,
                      COLORS["success"], padx=10, pady=4).pack(side="right", padx=4)

        self._books_tree = make_treeview(
            right,
            cols=("ID", "Title", "Author", "Genre", "ISBN",
                  "Total", "Available", "Added"),
            widths={"ID": 42, "Title": 220, "Author": 130, "Genre": 100,
                    "ISBN": 110, "Total": 50, "Available": 72, "Added": 140},
        )
        for col in ("ID", "Title", "Author", "Genre"):
            self._books_tree.heading(
                col, command=lambda c=col: self._sort_tree(self._books_tree, c))

    def _build_members_tab(self):
        frame = ttk.Frame(self.nb)
        self.nb.add(frame, text="  👥 Members  ")

        # ── left panel ────────────────────────────────────────────────────────
        left = side_panel(frame, "Register Member")

        self._m_entries = {
            "name" : labeled_entry(left, "Full Name  *"),
            "email": labeled_entry(left, "Email"),
            "phone": labeled_entry(left, "Phone"),
        }
        styled_button(left, "➕  Register Member", self._add_member,
                      COLORS["purple"], pady=8).pack(fill="x", padx=20, pady=10)

        divider(left, COLORS["panel_bg"])
        tk.Label(left, text="Issue Book", bg=COLORS["panel_bg"],
                 font=("Segoe UI", 13, "bold"),
                 fg=COLORS["text_dark"]).pack(pady=(4, 10))

        self._i_book_id   = labeled_entry(left, "Book ID  *")
        self._i_member_id = labeled_entry(left, "Member ID  *")

        tk.Label(left, text="Loan Duration", bg=COLORS["panel_bg"],
                 font=("Segoe UI", 10), anchor="w",
                 fg=COLORS["text_dark"]).pack(fill="x", padx=20)
        self._i_days = ttk.Combobox(left, values=["7", "14", "30", "60"],
                                    font=("Segoe UI", 10), state="readonly")
        self._i_days.set("14")
        self._i_days.pack(fill="x", padx=20, pady=(2, 14))

        styled_button(left, "📤  Issue Book", self._issue_book,
                      COLORS["warning"], pady=8).pack(fill="x", padx=20, pady=4)

        right = tk.Frame(frame)
        right.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=10)

        bar = tk.Frame(right)
        bar.pack(fill="x", pady=(0, 8))
        tk.Label(bar, text="🔍  Search:", font=("Segoe UI", 11)).pack(side="left")
        self._m_search = tk.StringVar()
        self._m_search.trace_add("write", lambda *_: self._refresh_members())
        tk.Entry(bar, textvariable=self._m_search,
                 font=("Segoe UI", 11), width=32,
                 relief="solid", bd=1).pack(side="left", padx=8, ipady=4)

        self._members_tree = make_treeview(
            right,
            cols=("ID", "Name", "Email", "Phone", "Join Date"),
            widths={"ID": 52, "Name": 200, "Email": 220, "Phone": 130, "Join Date": 170},
        )

    def _build_transactions_tab(self):
        frame = ttk.Frame(self.nb)
        self.nb.add(frame, text="  📋 Transactions  ")

        # ── control bar ───────────────────────────────────────────────────────
        ctrl = tk.Frame(frame)
        ctrl.pack(fill="x", padx=10, pady=10)

        tk.Label(ctrl, text="Return — Trans ID:",
                 font=("Segoe UI", 11)).pack(side="left")
        self._ret_id = tk.Entry(ctrl, font=("Segoe UI", 11),
                                width=9, relief="solid", bd=1)
        self._ret_id.pack(side="left", padx=6, ipady=4)
        styled_button(ctrl, "📥  Return Book", self._return_book,
                      COLORS["success"], padx=12, pady=5).pack(side="left", padx=6)

        tk.Label(ctrl, text="|", font=("Segoe UI", 14),
                 fg="#ccc").pack(side="left", padx=8)

        tk.Label(ctrl, text="Filter:", font=("Segoe UI", 11)).pack(side="left")
        self._t_filter = ttk.Combobox(
            ctrl, values=["All", "Active", "Returned", "Overdue"],
            font=("Segoe UI", 10), state="readonly", width=11)
        self._t_filter.set("All")
        self._t_filter.bind("<<ComboboxSelected>>",
                            lambda _: self._refresh_transactions())
        self._t_filter.pack(side="left", padx=6)

        tk.Label(ctrl, text="🔍", font=("Segoe UI", 11)).pack(side="left", padx=(14, 4))
        self._t_search = tk.StringVar()
        self._t_search.trace_add("write", lambda *_: self._refresh_transactions())
        tk.Entry(ctrl, textvariable=self._t_search,
                 font=("Segoe UI", 11), width=28,
                 relief="solid", bd=1).pack(side="left", padx=4, ipady=4)

        styled_button(ctrl, "📥 Export CSV", self._export_transactions,
                      COLORS["primary"], padx=10, pady=5).pack(side="right", padx=4)

        self._trans_tree = make_treeview(
            frame,
            cols=("ID", "Book", "Member", "Issued", "Due",
                  "Returned", "Fine (₹)", "Status"),
            widths={"ID": 50, "Book": 230, "Member": 170, "Issued": 140,
                    "Due": 95, "Returned": 140, "Fine (₹)": 80, "Status": 90},
            height=26,
        )

    def _add_book(self):
        title = self._b_entries["title"].get().strip()
        if not title:
            messagebox.showwarning("Required", "Book title cannot be empty."); return
        author = self._b_entries["author"].get().strip() or "Unknown"
        genre  = self._b_entries["genre"].get().strip()  or "General"
        isbn   = self._b_entries["isbn"].get().strip()
        copies = int(self._b_copies.get())
        self.db.add_book(title, author, genre, isbn, copies)
        messagebox.showinfo("✅ Added", f'"{title}" added to the library.')
        for e in self._b_entries.values(): e.delete(0, "end")
        self._refresh_books(); self._refresh_dashboard()

    def _delete_book(self):
        sel = self._books_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a book first."); return
        vals   = self._books_tree.item(sel[0])["values"]
        bid, btitle = vals[0], vals[1]
        if not messagebox.askyesno("Confirm", f'Delete "{btitle}"?'): return
        ok, msg = self.db.delete_book(bid)
        (messagebox.showinfo if ok else messagebox.showerror)("Result", msg)
        if ok:
            self._refresh_books(); self._refresh_dashboard()

    def _add_member(self):
        name = self._m_entries["name"].get().strip()
        if not name:
            messagebox.showwarning("Required", "Member name cannot be empty."); return
        email = self._m_entries["email"].get().strip()
        phone = self._m_entries["phone"].get().strip()
        self.db.add_member(name, email, phone)
        messagebox.showinfo("✅ Registered", f'"{name}" registered as a member.')
        for e in self._m_entries.values(): e.delete(0, "end")
        self._refresh_members(); self._refresh_dashboard()

    def _issue_book(self):
        bid = self._i_book_id.get().strip()
        mid = self._i_member_id.get().strip()
        if not (bid and mid):
            messagebox.showwarning("Required", "Book ID and Member ID are required."); return
        ok, msg = self.db.issue_book(bid, mid, int(self._i_days.get()))
        (messagebox.showinfo if ok else messagebox.showerror)(
            "✅ Issued" if ok else "❌ Failed", msg)
        if ok:
            self._i_book_id.delete(0, "end"); self._i_member_id.delete(0, "end")
            self._refresh_books(); self._refresh_transactions(); self._refresh_dashboard()

    def _return_book(self):
        tid = self._ret_id.get().strip()
        if not tid:
            messagebox.showwarning("Required", "Enter a Transaction ID."); return
        ok, msg, fine = self.db.return_book(tid)
        if ok:
            detail = f"{msg}"
            if fine > 0:
                detail += f"\n⚠️  Overdue fine collected: ₹{fine:.2f}"
            messagebox.showinfo("📥 Returned", detail)
            self._ret_id.delete(0, "end")
            self._refresh_books(); self._refresh_transactions(); self._refresh_dashboard()
        else:
            messagebox.showerror("❌ Error", msg)

    def _refresh_all(self):
        self._refresh_dashboard()
        self._refresh_books()
        self._refresh_members()
        self._refresh_transactions()

    def _refresh_dashboard(self):
        stats = self.db.get_stats()
        for key, lbl in self._stat_vals.items():
            v = stats.get(key, 0)
            lbl.config(text=f"₹{v:.0f}" if key == "total_fines" else str(v))

        for row in self._recent_tree.get_children():
            self._recent_tree.delete(row)
        today = datetime.date.today()
        for t in self.db.get_transactions()[:12]:
            tid, book, member, idate, ddate, rdate, fine, status = t
            tag  = self._txn_tag(status, ddate, today)
            self._recent_tree.insert("", "end",
                values=(tid, book, member,
                        idate[:10] if idate else "",
                        ddate or "", status),
                tags=(tag,))

    def _refresh_books(self):
        for row in self._books_tree.get_children():
            self._books_tree.delete(row)
        for b in self.db.get_books(self._b_search.get()):
            tag = "avail" if b[6] > 0 else "unavail"
            self._books_tree.insert("", "end", values=b, tags=(tag,))

    def _refresh_members(self):
        for row in self._members_tree.get_children():
            self._members_tree.delete(row)
        for m in self.db.get_members(self._m_search.get()):
            self._members_tree.insert("", "end", values=m)

    def _refresh_transactions(self):
        for row in self._trans_tree.get_children():
            self._trans_tree.delete(row)

        filt   = self._t_filter.get()
        search = self._t_search.get()
        status = None if filt in ("All", "Overdue") else filt
        today  = datetime.date.today()

        for t in self.db.get_transactions(status, search):
            tid, book, member, idate, ddate, rdate, fine, st = t

            if filt == "Overdue":
                if st != "Active" or not ddate: continue
                if datetime.datetime.strptime(ddate, "%Y-%m-%d").date() >= today: continue

            tag        = self._txn_tag(st, ddate, today)
            fine_disp  = f"₹{fine:.2f}" if fine else "—"
            rdate_disp = rdate[:10] if rdate else "—"
            self._trans_tree.insert("", "end",
                values=(tid, book, member,
                        idate[:10] if idate else "",
                        ddate or "—", rdate_disp, fine_disp, st),
                tags=(tag,))

    @staticmethod
    def _txn_tag(status, due_date, today=None):
        if status == "Returned": return "returned"
        if today and due_date:
            d = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
            if today > d: return "overdue"
        return "active"
    
    def _export_books(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="books_export.csv")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID","Title","Author","Genre","ISBN",
                        "Total","Available","Added Date"])
            w.writerows(self.db.get_books())
        messagebox.showinfo("✅ Exported", f"Books saved to:\n{path}")

    def _export_transactions(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="transactions_export.csv")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID","Book","Member","Issued","Due",
                        "Returned","Fine (₹)","Status"])
            w.writerows(self.db.get_transactions())
        messagebox.showinfo("✅ Exported", f"Transactions saved to:\n{path}")

    
    _sort_reverse: dict = {}

    def _sort_tree(self, tree, col):
        rev = self._sort_reverse.get(col, False)
        data = [(tree.set(c, col), c) for c in tree.get_children("")]
        try:
            data.sort(key=lambda x: int(x[0]), reverse=rev)
        except ValueError:
            data.sort(key=lambda x: x[0].lower(), reverse=rev)
        for i, (_, child) in enumerate(data):
            tree.move(child, "", i)
        self._sort_reverse[col] = not rev

   
    def run(self):
        self.root.mainloop()



if __name__ == "__main__":
    LibraryApp().run()
