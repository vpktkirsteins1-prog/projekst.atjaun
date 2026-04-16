import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import hashlib
import json
import urllib.request
import re

DB_FILE = "budzets.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_exchange_rate(base_currency="EUR", target_currency="USD"):
    url = f"https://open.er-api.com/v6/latest/{base_currency}"

    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))

    if data.get("result") != "success":
        raise Exception("API neatgrieza veiksmīgu atbildi.")

    rates = data.get("rates", {})
    if target_currency not in rates:
        raise Exception(f"Nav atrasts kurss valūtai: {target_currency}")

    return rates[target_currency]


def ensure_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            blocked BOOLEAN NOT NULL DEFAULT 0,
            active_from DATE NOT NULL DEFAULT (date('now')),
            active_until DATE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_code TEXT NOT NULL,
            unique_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            FOREIGN KEY (user_id) REFERENCES user(user_id)
                ON DELETE CASCADE
                ON UPDATE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id)
                ON DELETE SET NULL
                ON UPDATE CASCADE
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ("EXPENSE", "FOOD", "Pārtika"),
            ("EXPENSE", "TRANSPORT", "Transports"),
            ("EXPENSE", "ENTERTAINMENT", "Izklaide"),
            ("EXPENSE", "OTHER_EXPENSE", "Citi izdevumi"),
            ("INCOME", "SALARY", "Alga"),
            ("INCOME", "OTHER_INCOME", "Citi ienākumi")
        ]
        cursor.executemany("""
            INSERT INTO categories (group_code, unique_code, name)
            VALUES (?, ?, ?)
        """, default_categories)

    conn.commit()
    conn.close()


ensure_database()


class BudgetApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Personīgā budžeta aplikācija")
        self.root.geometry("1120x680")
        self.root.configure(bg="#f4f6f8")

        self.current_user_id = None
        self.current_username = None

        self.table = None
        self.balance_label = None
        self.status_label = None
        self.entry_amount = None
        self.entry_description = None
        self.type_var = None
        self.currency_var = None
        self.converted_balance_label = None
        self.category_var = None
        self.category_combo = None

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("Treeview", rowheight=28, font=("Arial", 11))
        self.style.configure("Treeview.Heading", font=("Arial", 11, "bold"))
        self.style.configure("TButton", font=("Arial", 11))
        self.style.configure("TLabel", font=("Arial", 11))

        self.show_login_screen()

    def clear_root(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login_screen(self):
        self.clear_root()

        container = tk.Frame(self.root, bg="#f4f6f8")
        container.pack(expand=True)

        card = tk.Frame(container, bg="white", bd=1, relief="solid", padx=30, pady=30)
        card.pack()

        tk.Label(
            card,
            text="Personīgā budžeta aplikācija",
            font=("Arial", 20, "bold"),
            bg="white",
            fg="#1f2937"
        ).grid(row=0, column=0, columnspan=2, pady=(0, 20))

        tk.Label(card, text="Lietotājvārds", bg="white", font=("Arial", 11)).grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.login_username_entry = ttk.Entry(card, width=30)
        self.login_username_entry.grid(row=1, column=1, pady=5)

        tk.Label(card, text="Parole", bg="white", font=("Arial", 11)).grid(
            row=2, column=0, sticky="w", pady=5
        )
        self.login_password_entry = ttk.Entry(card, width=30, show="*")
        self.login_password_entry.grid(row=2, column=1, pady=5)

        ttk.Button(card, text="Ielogoties", command=self.login).grid(
            row=3, column=0, pady=15, padx=5
        )
        ttk.Button(card, text="Reģistrēties", command=self.register).grid(
            row=3, column=1, pady=15, padx=5
        )

    def user_exists(self, username):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM user WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def validate_user(self, username, password):
        password_hash = hash_password(password)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username
            FROM user
            WHERE username = ?
              AND password_hash = ?
              AND blocked = 0
              AND date('now') >= active_from
              AND (active_until IS NULL OR date('now') <= active_until)
        """, (username, password_hash))
        result = cursor.fetchone()
        conn.close()
        return result

    def register(self):
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Kļūda", "Aizpildi lietotājvārdu un paroli.")
            return

        if len(password) < 8:
            messagebox.showerror("Kļūda", "Parolei jābūt vismaz 8 simbolus garai.")
            return

        if not re.search(r"\d", password):
            messagebox.showerror("Kļūda", "Parolei jāsatur vismaz 1 cipars.")
            return

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            messagebox.showerror("Kļūda", "Parolei jāsatur vismaz 1 speciālais simbols.")
            return

        if self.user_exists(username):
            messagebox.showerror("Kļūda", "Šāds lietotājs jau eksistē.")
            return

        password_hash = hash_password(password)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user (username, password_hash, blocked, active_from, active_until)
            VALUES (?, ?, 0, date('now'), NULL)
        """, (username, password_hash))
        conn.commit()
        conn.close()

        messagebox.showinfo("Veiksmīgi", "Lietotājs reģistrēts. Tagad vari ielogoties.")
        self.login_username_entry.delete(0, tk.END)
        self.login_password_entry.delete(0, tk.END)

    def login(self):
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get().strip()

        result = self.validate_user(username, password)
        if result:
            self.current_user_id = result[0]
            self.current_username = result[1]
            self.show_main_app()
        else:
            messagebox.showerror(
                "Kļūda",
                "Nepareizs lietotājvārds vai parole, vai lietotājs nav aktīvs."
            )

    def logout(self):
        self.current_user_id = None
        self.current_username = None
        self.show_login_screen()

    def load_categories(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories ORDER BY name")
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()

        self.category_combo["values"] = categories
        if categories:
            self.category_var.set(categories[0])

    def show_main_app(self):
        self.clear_root()

        app_frame = tk.Frame(self.root, bg="#f4f6f8")
        app_frame.pack(fill="both", expand=True, padx=20, pady=20)

        top_bar = tk.Frame(app_frame, bg="#f4f6f8")
        top_bar.pack(fill="x", pady=(0, 10))

        tk.Label(
            top_bar,
            text=f"Personīgā budžeta pārvaldība — {self.current_username}",
            font=("Arial", 20, "bold"),
            bg="#f4f6f8",
            fg="#1f2937"
        ).pack(side="left")

        ttk.Button(top_bar, text="Izlogoties", command=self.logout).pack(side="right")

        input_card = tk.Frame(app_frame, bg="white", bd=1, relief="solid", padx=15, pady=15)
        input_card.pack(fill="x", pady=(0, 15))

        self.type_var = tk.StringVar(value="Izdevums")
        self.category_var = tk.StringVar()

        tk.Label(input_card, text="Tips", bg="white", font=("Arial", 11)).grid(row=0, column=0, padx=8, pady=8)
        ttk.Combobox(
            input_card,
            textvariable=self.type_var,
            values=["Ienākums", "Izdevums"],
            state="readonly",
            width=15
        ).grid(row=0, column=1, padx=8, pady=8)

        tk.Label(input_card, text="Kategorija", bg="white", font=("Arial", 11)).grid(row=0, column=2, padx=8, pady=8)
        self.category_combo = ttk.Combobox(
            input_card,
            textvariable=self.category_var,
            state="readonly",
            width=18
        )
        self.category_combo.grid(row=0, column=3, padx=8, pady=8)
        self.load_categories()

        tk.Label(input_card, text="Summa", bg="white", font=("Arial", 11)).grid(row=0, column=4, padx=8, pady=8)
        self.entry_amount = ttk.Entry(input_card, width=18)
        self.entry_amount.grid(row=0, column=5, padx=8, pady=8)

        tk.Label(input_card, text="Apraksts", bg="white", font=("Arial", 11)).grid(row=0, column=6, padx=8, pady=8)
        self.entry_description = ttk.Entry(input_card, width=25)
        self.entry_description.grid(row=0, column=7, padx=8, pady=8)

        ttk.Button(input_card, text="Pievienot", command=self.add_record).grid(row=0, column=8, padx=12, pady=8)

        table_card = tk.Frame(app_frame, bg="white", bd=1, relief="solid", padx=10, pady=10)
        table_card.pack(fill="both", expand=True)

        columns = ("ID", "Tips", "Kategorija", "Summa", "Apraksts")
        self.table = ttk.Treeview(table_card, columns=columns, show="headings")
        self.table.heading("ID", text="ID")
        self.table.heading("Tips", text="Tips")
        self.table.heading("Kategorija", text="Kategorija")
        self.table.heading("Summa", text="Summa (€)")
        self.table.heading("Apraksts", text="Apraksts")

        self.table.column("ID", width=70, anchor="center")
        self.table.column("Tips", width=120, anchor="center")
        self.table.column("Kategorija", width=160, anchor="center")
        self.table.column("Summa", width=140, anchor="center")
        self.table.column("Apraksts", width=320, anchor="w")

        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)

        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        bottom_bar = tk.Frame(app_frame, bg="#f4f6f8")
        bottom_bar.pack(fill="x", pady=(15, 0))

        left_buttons = tk.Frame(bottom_bar, bg="#f4f6f8")
        left_buttons.pack(side="left")

        ttk.Button(left_buttons, text="Dzēst izvēlēto", command=self.delete_selected).pack(side="left", padx=5)
        ttk.Button(left_buttons, text="Dzēst visus manus ierakstus", command=self.delete_all).pack(side="left", padx=5)

        self.balance_label = tk.Label(
            bottom_bar,
            text="Bilance: 0.00 €",
            font=("Arial", 16, "bold"),
            bg="#f4f6f8",
            fg="#111827"
        )
        self.balance_label.pack(side="right")

        currency_frame = tk.Frame(app_frame, bg="#f4f6f8")
        currency_frame.pack(fill="x", pady=(8, 0))

        tk.Label(currency_frame, text="Valūta:", bg="#f4f6f8", font=("Arial", 11)).pack(side="left")

        self.currency_var = tk.StringVar(value="USD")

        ttk.Combobox(
            currency_frame,
            textvariable=self.currency_var,
            values=["USD", "GBP", "CHF", "JPY"],
            state="readonly",
            width=10
        ).pack(side="left", padx=8)

        ttk.Button(
            currency_frame,
            text="Konvertēt bilanci",
            command=self.convert_balance
        ).pack(side="left", padx=8)

        self.converted_balance_label = tk.Label(
            currency_frame,
            text="Bilance citā valūtā: -",
            font=("Arial", 11),
            bg="#f4f6f8",
            fg="#111827"
        )
        self.converted_balance_label.pack(side="left", padx=12)

        self.status_label = tk.Label(
            app_frame,
            text="",
            font=("Arial", 10),
            bg="#f4f6f8",
            fg="#b91c1c"
        )
        self.status_label.pack(anchor="w", pady=(8, 0))

        self.load_records()
        self.calculate_balance()

    def add_record(self):
        record_type = self.type_var.get()
        category_name = self.category_var.get()
        amount_text = self.entry_amount.get().strip()
        description = self.entry_description.get().strip()

        if not amount_text:
            self.status_label.config(text="Ievadi summu.")
            return

        try:
            amount = float(amount_text)
        except ValueError:
            self.status_label.config(text="Summai jābūt skaitlim.")
            return

        if amount <= 0:
            self.status_label.config(text="Summai jābūt lielākai par 0.")
            return

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
        category_row = cursor.fetchone()
        category_id = category_row[0] if category_row else None

        cursor.execute("""
            INSERT INTO records (user_id, category_id, type, amount, description)
            VALUES (?, ?, ?, ?, ?)
        """, (self.current_user_id, category_id, record_type, amount, description))

        conn.commit()
        conn.close()

        self.entry_amount.delete(0, tk.END)
        self.entry_description.delete(0, tk.END)
        self.status_label.config(text="Ieraksts veiksmīgi pievienots.")
        self.load_records()
        self.calculate_balance()

    def load_records(self):
        for row in self.table.get_children():
            self.table.delete(row)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT records.id, records.type, categories.name, records.amount, records.description
            FROM records
            LEFT JOIN categories ON records.category_id = categories.id
            WHERE records.user_id = ?
        """, (self.current_user_id,))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            self.table.insert("", tk.END, values=row)

    def calculate_balance(self):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM records
            WHERE user_id = ? AND type = 'Ienākums'
        """, (self.current_user_id,))
        income = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM records
            WHERE user_id = ? AND type = 'Izdevums'
        """, (self.current_user_id,))
        expense = cursor.fetchone()[0]

        conn.close()

        balance = income - expense
        self.balance_label.config(text=f"Bilance: {balance:.2f} €")

    def convert_balance(self):
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM records
                WHERE user_id = ? AND type = 'Ienākums'
            """, (self.current_user_id,))
            income = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0)
                FROM records
                WHERE user_id = ? AND type = 'Izdevums'
            """, (self.current_user_id,))
            expense = cursor.fetchone()[0]

            conn.close()

            balance_eur = income - expense
            target_currency = self.currency_var.get()

            rate = get_exchange_rate("EUR", target_currency)
            converted_balance = balance_eur * rate

            self.converted_balance_label.config(
                text=f"Bilance {target_currency}: {converted_balance:.2f}"
            )
            self.status_label.config(text="Bilance veiksmīgi konvertēta.")
        except Exception as e:
            self.status_label.config(text=f"Neizdevās iegūt valūtas kursu no API. {e}")

    def delete_selected(self):
        selected = self.table.selection()

        if not selected:
            self.status_label.config(text="Izvēlies ierakstu, ko dzēst.")
            return

        values = self.table.item(selected[0])["values"]
        record_id = values[0]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM records
            WHERE id = ? AND user_id = ?
        """, (record_id, self.current_user_id))
        conn.commit()
        conn.close()

        self.status_label.config(text="Izvēlētais ieraksts izdzēsts.")
        self.load_records()
        self.calculate_balance()

    def delete_all(self):
        confirm = messagebox.askyesno(
            "Apstiprinājums",
            "Vai tiešām dzēst visus šī lietotāja ierakstus?"
        )
        if not confirm:
            return

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM records
            WHERE user_id = ?
        """, (self.current_user_id,))
        conn.commit()
        conn.close()

        self.status_label.config(text="Visi tavi ieraksti izdzēsti.")
        self.load_records()
        self.calculate_balance()


if __name__ == "__main__":
    root = tk.Tk()
    app = BudgetApp(root)
    root.mainloop()