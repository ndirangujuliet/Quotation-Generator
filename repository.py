from datetime import date, timedelta
from db import get_conn, rows_as_dicts


def _one(cur):
    rows = rows_as_dicts(cur)
    return rows[0] if rows else None


# ---------- customers and products ----------

def get_customers():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, kra_pin FROM customers ORDER BY name")
        return rows_as_dicts(cur)


def get_products():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, unit_price, tax_category FROM products ORDER BY name")
        return rows_as_dicts(cur)


# ---------- quotes ----------

def save_quote(customer_id, result, valid_days, currency, terms):
    """Saves the quote and its lines in ONE transaction. Returns the quote id."""
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO quotes
               (quote_no, customer_id, issue_date, valid_until, currency, vat_rate,
                discount_percent, discount_total, subtotal, total_vat, grand_total, terms)
               OUTPUT INSERTED.id
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TEMP", customer_id, today, today + timedelta(days=valid_days), currency,
             result["vat_rate"], result["discount_percent"], result["discount_total"],
             result["subtotal"], result["total_vat"], result["grand_total"], terms),
        )
        quote_id = cur.fetchone()[0]

        quote_no = f"QT-{today.year}-{quote_id:04d}"
        cur.execute("UPDATE quotes SET quote_no = ? WHERE id = ?", (quote_no, quote_id))

        cur.executemany(
            """INSERT INTO quote_items
               (quote_id, description, qty, unit_price, tax_category,
                line_net, line_discount, line_vat)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(quote_id, i["description"], i["qty"], i["unit_price"], i["tax_category"],
              i["line_net"], i["line_discount"], i["line_vat"])
             for i in result["items"]],
        )
        return quote_id


def get_quote(quote_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT q.*, c.name AS customer_name, c.kra_pin, c.address, c.email, c.phone
               FROM quotes q JOIN customers c ON c.id = q.customer_id
               WHERE q.id = ?""", (quote_id,))
        quote = _one(cur)
        if quote is None:
            return None
        cur.execute("SELECT * FROM quote_items WHERE quote_id = ? ORDER BY id", (quote_id,))
        quote["items"] = rows_as_dicts(cur)
        return quote


def list_quotes():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT q.id, q.quote_no, q.issue_date, q.currency, q.grand_total,
                      c.name AS customer_name
               FROM quotes q JOIN customers c ON c.id = q.customer_id
               ORDER BY q.id DESC""")
        return rows_as_dicts(cur)


# ---------- company settings ----------

def get_settings():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM company_settings WHERE id = 1")
        return _one(cur)


def save_settings(d):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE company_settings
               SET name = ?, email = ?, phone = ?, address = ?, kra_pin = ?,
                   vat_rate = ?, default_currency = ?, default_valid_days = ?,
                   default_terms = ?
               WHERE id = 1""",
            (d["name"], d["email"], d["phone"], d["address"], d["kra_pin"],
             d["vat_rate"], d["default_currency"], d["default_valid_days"],
             d["default_terms"]),
        )


def save_logo(filename):
    """filename = new logo file name, or None to remove the logo."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE company_settings SET logo_file = ? WHERE id = 1", (filename,))


# ---------- users ----------

def count_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def count_active_admins():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1")
        return cur.fetchone()[0]


def get_user(user_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, role, is_active, last_login
               FROM users WHERE id = ?""", (user_id,))
        return _one(cur)


def get_user_by_username(username):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, password_hash, role, is_active,
                      CASE WHEN locked_until > SYSDATETIME()
                           THEN DATEDIFF(MINUTE, SYSDATETIME(), locked_until) + 1
                           ELSE 0 END AS lock_minutes_left
               FROM users WHERE username = ?""", (username,))
        return _one(cur)


def list_users():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, username, full_name, role, is_active, last_login
               FROM users ORDER BY full_name""")
        return rows_as_dicts(cur)


def create_user(username, full_name, password_hash, role):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users (username, full_name, password_hash, role)
               VALUES (?, ?, ?, ?)""",
            (username, full_name, password_hash, role))


def set_password(user_id, password_hash):
    """Also clears any lockout, so resetting a password unlocks the account."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL
               WHERE id = ?""", (password_hash, user_id))


def set_active(user_id, active):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, user_id))


def record_login_success(user_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE users SET failed_attempts = 0, locked_until = NULL,
                                last_login = SYSDATETIME()
               WHERE id = ?""", (user_id,))


def record_login_failure(user_id, max_attempts, lock_minutes):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE users SET
                   locked_until = CASE WHEN failed_attempts + 1 >= ?
                                       THEN DATEADD(MINUTE, ?, SYSDATETIME())
                                       ELSE locked_until END,
                   failed_attempts = CASE WHEN failed_attempts + 1 >= ?
                                          THEN 0 ELSE failed_attempts + 1 END
               WHERE id = ?""",
            (max_attempts, lock_minutes, max_attempts, user_id))