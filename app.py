import os
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, flash,
                   abort, g, session)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from calc import calculate_quote, QuoteError, CATEGORIES
import repository as repo

app = Flask(__name__)
app.config.from_object(Config)
csrf = CSRFProtect(app)          # adds CSRF checks to every POST form

ALLOWED_LOGO = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_ATTEMPTS = 5                 # wrong passwords before the account locks
LOCK_MINUTES = 15
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")
PHONE_CHARS_RE = re.compile(r"\+?[0-9 ()\-]+")
PHONE_ERROR = ("Enter a valid phone number: 10 digits starting with 0 (e.g. 0712345678) "
               "or international format (e.g. +254712345678).")
DUMMY_HASH = generate_password_hash("not-a-real-password")   # keeps timing similar for unknown usernames
PUBLIC_ENDPOINTS = {"login", "setup", "static"}


class SettingsError(ValueError):
    """Raised when the settings form is invalid."""


class CustomerError(ValueError):
    """Raised when the customer form is invalid."""


# ---------- settings, globals ----------

def settings():
    """Company settings, loaded once per request."""
    if "settings" not in g:
        g.settings = repo.get_settings()
        if g.settings is None:
            raise RuntimeError("company_settings has no row. Run the SQL script that creates it.")
    return g.settings


@app.template_filter("money")
def money_filter(value):
    return "{:,.2f}".format(value)


@app.context_processor
def inject_globals():
    s = settings()
    return {
        "company": {
            "name": s["name"], "email": s["email"], "phone": s["phone"],
            "address": s["address"], "kra_pin": s["kra_pin"],
            "logo": ("uploads/" + s["logo_file"]) if s["logo_file"] else "",
        },
        "defaults": {
            "currency": s["default_currency"],
            "valid_days": s["default_valid_days"],
            "terms": s["default_terms"] or "",
        },
        "today": date.today().isoformat(),
        "current_user": g.get("user"),
    }


# ---------- login protection ----------

@app.before_request
def load_user_and_require_login():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        user = repo.get_user(user_id)
        if user and user["is_active"]:
            g.user = user
        else:
            session.clear()          # deleted or deactivated: sign them out at once

    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if g.user is None:
        if repo.count_users() == 0:
            return redirect(url_for("setup"))
        nxt = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("login", next=nxt))
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def safe_next(target):
    """Only allow redirects to pages inside this app."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("quotes")


def check_new_password(password, confirm, username=""):
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password is too long (maximum 128 characters)."
    if password != confirm:
        return "The two passwords do not match."
    if username and password.lower() == username.lower():
        return "Password cannot be the same as the username."
    return None


def check_new_user(full_name, username):
    if not full_name:
        return "Full name is required."
    if not USERNAME_RE.match(username):
        return "Username must be 3 to 50 characters: letters, numbers, dot, dash or underscore."
    if repo.get_user_by_username(username):
        return "That username is already taken."
    return None


def text_field(form, field, limit):
    """Trimmed text from a form field, cut to `limit` characters. None if empty."""
    return (form.get(field) or "").strip()[:limit] or None


def clean_phone(value, error_cls):
    """Returns the phone number in a standard form (digits, optional leading +).
    None if blank. Raises error_cls if it is not a valid number."""
    value = (value or "").strip()
    if not value:
        return None
    if not PHONE_CHARS_RE.fullmatch(value):
        raise error_cls(PHONE_ERROR)

    number = re.sub(r"[ ()\-]", "", value)            # drop spaces, dashes, brackets
    if re.fullmatch(r"254[0-9]{9}", number):          # 254712345678 -> +254712345678
        number = "+" + number

    kenyan_local = re.fullmatch(r"0[0-9]{9}", number)
    international = re.fullmatch(r"\+[0-9]{8,15}", number)
    if number.startswith("+254") and len(number) != 13:
        international = None                          # Kenyan numbers are +254 and 9 digits
    if not (kenyan_local or international):
        raise error_cls(PHONE_ERROR)
    return number


# ---------- sign in / out ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("quotes"))
    if repo.count_users() == 0:
        return redirect(url_for("setup"))

    error = None
    username = ""
    next_url = request.form.get("next") or request.args.get("next") or ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = repo.get_user_by_username(username) if username else None

        if user and user["lock_minutes_left"] > 0:
            error = (f"Too many failed attempts. Try again in "
                     f"{user['lock_minutes_left']} minute(s).")
        else:
            password_ok = check_password_hash(
                user["password_hash"] if user else DUMMY_HASH, password)
            if user and password_ok and user["is_active"]:
                repo.record_login_success(user["id"])
                session.clear()                          # new session on every sign-in
                session["user_id"] = user["id"]
                session.permanent = bool(request.form.get("remember"))
                return redirect(safe_next(next_url))
            if user and password_ok:
                error = "This account has been deactivated. Please ask an administrator."
            else:
                if user:
                    repo.record_login_failure(user["id"], MAX_ATTEMPTS, LOCK_MINUTES)
                error = "Incorrect username or password."

    return render_template("login.html", error=error, username=username, next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "ok")
    return redirect(url_for("login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """First run only: create the administrator account."""
    if repo.count_users() > 0:
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()[:100]
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        error = check_new_user(full_name, username) or check_new_password(password, confirm, username)
        if error:
            flash(error, "error")
        else:
            repo.create_user(username, full_name, generate_password_hash(password), "admin")
            flash("Administrator account created. Please sign in.", "ok")
            return redirect(url_for("login"))

    return render_template("setup.html")


@app.route("/account", methods=["GET", "POST"])
def account():
    """Any signed-in user can change their own password."""
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        full = repo.get_user_by_username(g.user["username"])
        error = None
        if not check_password_hash(full["password_hash"], current):
            error = "Your current password is incorrect."
        else:
            error = check_new_password(new, confirm, g.user["username"])
        if error:
            flash(error, "error")
        else:
            repo.set_password(g.user["id"], generate_password_hash(new))
            flash("Password changed.", "ok")
            return redirect(url_for("account"))
    return render_template("account.html")


# ---------- users (admin) ----------

@app.route("/users")
@admin_required
def users():
    return render_template("users.html", users=repo.list_users())


@app.route("/users/new", methods=["POST"])
@admin_required
def user_new():
    full_name = request.form.get("full_name", "").strip()[:100]
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "staff")
    password = request.form.get("password", "")
    error = (check_new_user(full_name, username)
             or check_new_password(password, password, username))
    if role not in ("admin", "staff"):
        error = "Invalid role."
    if error:
        flash(error, "error")
    else:
        repo.create_user(username, full_name, generate_password_hash(password), role)
        flash(f"User {username} created. Share the temporary password privately.", "ok")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/password", methods=["POST"])
@admin_required
def user_password(user_id):
    target = repo.get_user(user_id)
    if target is None:
        abort(404)
    password = request.form.get("password", "")
    error = check_new_password(password, password, target["username"])
    if error:
        flash(error, "error")
    else:
        repo.set_password(user_id, generate_password_hash(password))
        flash(f"Password reset for {target['username']}.", "ok")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def user_toggle(user_id):
    target = repo.get_user(user_id)
    if target is None:
        abort(404)
    if target["id"] == g.user["id"]:
        flash("You cannot deactivate your own account.", "error")
    elif target["is_active"] and target["role"] == "admin" and repo.count_active_admins() <= 1:
        flash("There must be at least one active administrator.", "error")
    else:
        repo.set_active(user_id, not target["is_active"])
        flash(f"{target['username']} is now {'inactive' if target['is_active'] else 'active'}.", "ok")
    return redirect(url_for("users"))


# ---------- quotes ----------

def parse_items(form):
    """Reads the repeated form fields into a list of item dicts."""
    return [
        {"description": d, "qty": q, "unit_price": p, "tax_category": t}
        for d, q, p, t in zip(
            form.getlist("description"),
            form.getlist("qty"),
            form.getlist("unit_price"),
            form.getlist("tax_category"),
        )
        if d.strip() or q or p            # ignore fully blank rows
    ]


def read_quote_form(form):
    s = settings()
    customer_id = None
    new_customer = None

    if form.get("customer_id") == "new":
        name = text_field(form, "new_name", 200)
        if not name:
            raise QuoteError("Please enter the customer's name.")
        new_customer = {
            "name": name,
            "kra_pin": text_field(form, "new_kra_pin", 30),
            "address": text_field(form, "new_address", 300),
            "email": text_field(form, "new_email", 150),
            "phone": clean_phone(form.get("new_phone"), QuoteError),
        }
    else:
        try:
            customer_id = int(form.get("customer_id", ""))
        except ValueError:
            raise QuoteError("Please select a customer.")

    try:
        valid_days = int(form.get("valid_days") or s["default_valid_days"])
    except ValueError:
        raise QuoteError("Valid days must be a whole number.")
    if valid_days < 1:
        raise QuoteError("Valid days must be at least 1.")

    return {
        "customer_id": customer_id,
        "new_customer": new_customer,
        "valid_days": valid_days,
        "currency": (form.get("currency") or s["default_currency"]).strip().upper()[:10],
        "discount_percent": form.get("discount_percent") or "0",
        "terms": (form.get("terms") or "").strip()[:1000],
        "items": parse_items(form),
    }


@app.route("/")
def index():
    return redirect(url_for("quotes"))


@app.route("/quotes")
def quotes():
    return render_template("quotes.html", quotes=repo.list_quotes())


@app.route("/quotes/new", methods=["GET", "POST"])
def new_quote():
    vat_rate = settings()["vat_rate"]
    if request.method == "POST":
        try:
            data = read_quote_form(request.form)
            # The SERVER does the maths. Totals from the browser are never trusted.
            result = calculate_quote(data["items"], vat_rate, data["discount_percent"])
        except QuoteError as e:
            flash(str(e), "error")
        else:
            customer_id = data["customer_id"]
            if data["new_customer"]:
                customer_id = repo.create_customer(**data["new_customer"])
            quote_id = repo.save_quote(customer_id, result, data["valid_days"],
                                       data["currency"], data["terms"])
            return redirect(url_for("view_quote", quote_id=quote_id))

    return render_template(
        "quote_form.html",
        customers=repo.get_customers(),
        products=repo.get_products(),
        vat_rate=vat_rate,
    )


@app.route("/quotes/<int:quote_id>")
def view_quote(quote_id):
    quote = repo.get_quote(quote_id)
    if quote is None:
        abort(404)

    summary = {c: {"net": Decimal("0.00"), "vat": Decimal("0.00")} for c in CATEGORIES}
    for i in quote["items"]:
        summary[i["tax_category"]]["net"] += i["line_net"] - i["line_discount"]
        summary[i["tax_category"]]["vat"] += i["line_vat"]

    return render_template("quote_view.html", quote=quote, summary=summary)

@app.route("/quotes/<int:quote_id>/delete", methods=["POST"])
@admin_required
def quote_delete(quote_id):
    quote = repo.get_quote(quote_id)
    if quote is None:
        abort(404)
    repo.delete_quote(quote_id)
    flash(f"Quote {quote['quote_no']} deleted.", "ok")
    return redirect(url_for("quotes"))


# ---------- customers ----------

def read_customer_form(form):
    name = text_field(form, "name", 200)
    if not name:
        raise CustomerError("Customer name is required.")
    return {
        "name": name,
        "kra_pin": text_field(form, "kra_pin", 30),
        "address": text_field(form, "address", 300),
        "email": text_field(form, "email", 150),
        "phone": clean_phone(form.get("phone"), CustomerError),
    }


@app.route("/customers")
def customers():
    return render_template("customers.html", customers=repo.list_customers())


@app.route("/customers/new", methods=["GET", "POST"])
def customer_new():
    c = {}
    if request.method == "POST":
        c = request.form.to_dict()
        try:
            data = read_customer_form(request.form)
        except CustomerError as e:
            flash(str(e), "error")
        else:
            repo.create_customer(**data)
            flash("Customer added.", "ok")
            return redirect(url_for("customers"))
    return render_template("customer_form.html", c=c, editing=False)


@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def customer_edit(customer_id):
    c = repo.get_customer(customer_id)
    if c is None:
        abort(404)
    if request.method == "POST":
        c = {**c, **request.form.to_dict()}          # keep what was typed if there is an error
        try:
            data = read_customer_form(request.form)
        except CustomerError as e:
            flash(str(e), "error")
        else:
            repo.update_customer(customer_id, **data)
            flash("Customer updated.", "ok")
            return redirect(url_for("customers"))
    return render_template("customer_form.html", c=c, editing=True)


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
@admin_required
def customer_delete(customer_id):
    c = repo.get_customer(customer_id)
    if c is None:
        abort(404)
    if repo.count_customer_quotes(customer_id) > 0:
        flash(f"{c['name']} has quotes and cannot be deleted.", "error")
    else:
        repo.delete_customer(customer_id)
        flash(f"{c['name']} deleted.", "ok")
    return redirect(url_for("customers"))


# ---------- company settings (admin) ----------

def read_settings_form(form):
    name = form.get("name", "").strip()
    if not name:
        raise SettingsError("Company name is required.")

    try:
        vat_rate = Decimal(form.get("vat_rate", "").strip())
    except InvalidOperation:
        raise SettingsError("VAT rate must be a number.")
    if vat_rate < 0 or vat_rate > 100:
        raise SettingsError("VAT rate must be between 0 and 100.")

    try:
        valid_days = int(form.get("default_valid_days", ""))
    except ValueError:
        raise SettingsError("Default validity must be a whole number of days.")
    if valid_days < 1:
        raise SettingsError("Default validity must be at least 1 day.")

    def text(field, limit):
        return (form.get(field) or "").strip()[:limit] or None

    return {
        "name": name[:150],
        "email": text("email", 150),
        "phone": text("phone", 40),
        "address": text("address", 255),
        "kra_pin": text("kra_pin", 20),
        "vat_rate": vat_rate,
        "default_currency": (form.get("default_currency") or "").strip().upper()[:10] or "KES",
        "default_valid_days": valid_days,
        "default_terms": text("default_terms", 1000),
    }


def logo_folder():
    folder = os.path.join(app.static_folder, "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder


def clear_logo_files():
    folder = logo_folder()
    for f in os.listdir(folder):
        if f.startswith("logo-"):
            os.remove(os.path.join(folder, f))


def save_logo_file(file):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_LOGO:
        raise SettingsError("Logo must be a PNG, JPG, GIF or WEBP image.")
    clear_logo_files()
    filename = f"logo-{int(time.time())}.{ext}"     # new name each time, so browsers don't show an old cached logo
    file.save(os.path.join(logo_folder(), filename))
    return filename


@app.route("/settings", methods=["GET", "POST"])
@admin_required
def company_settings():
    if request.method == "POST":
        try:
            data = read_settings_form(request.form)
            logo = request.files.get("logo")
            new_logo = save_logo_file(logo) if logo and logo.filename else None
        except SettingsError as e:
            flash(str(e), "error")
        else:
            repo.save_settings(data)
            if new_logo:
                repo.save_logo(new_logo)
            elif request.form.get("remove_logo"):
                clear_logo_files()
                repo.save_logo(None)
            flash("Settings saved.", "ok")
            return redirect(url_for("company_settings"))

    return render_template("settings.html", s=settings())


# ---------- error pages ----------

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           message="You don't have permission to open this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="That page was not found."), 404


@app.errorhandler(413)
def too_large(e):
    flash("That file is too large. The logo must be under 2 MB.", "error")
    return redirect(url_for("company_settings"))


@app.errorhandler(CSRFError)
def csrf_error(e):
    flash("Your page expired. Please try again.", "error")
    return redirect(url_for("quotes"))


if __name__ == "__main__":
    app.run(debug=True)