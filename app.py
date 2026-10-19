from flask import (Flask, render_template, request, redirect,
                   url_for, flash, session, Response)
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from apscheduler.schedulers.background import BackgroundScheduler
import csv, os, secrets, smtplib, atexit, threading, io
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────
def _load_local_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

_load_local_env()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "med_alert_dev_key_not_for_production")

# Register Jinja helpers so templates never crash on type casting/math
app.jinja_env.globals.update(
    float=float,
    int=int,
    len=len,
    round=round,
    str=str,
    max=max,
    min=min,
    today=date.today
)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "⚠ You need to login first to access this page."
login_manager.login_message_category = "warning"

# ─────────────────────────────────────────────
# Base Paths
# ─────────────────────────────────────────────
_DIR       = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(_DIR, "users.csv")
DATA_DIR   = os.path.join(_DIR, "data")

FIELDNAMES      = ["medicine_id","medicine_name","batch_number","quantity","expiry_date","price"]
SUPPLIER_FIELDS = ["medicine_id","supplier_name","contact_number","email"]
RESTOCK_FIELDS  = ["timestamp","medicine_id","medicine_name","old_quantity","new_quantity","changed_by"]
USAGE_FIELDS    = ["timestamp","medicine_id","medicine_name","qty_used","qty_before","qty_after","dispensed_by","note"]
USER_FIELDS     = ["username","password","mobile","email","role"]

DATE_FORMAT = "%Y-%m-%d"
TS_FORMAT   = "%Y-%m-%d %H:%M:%S"
MIN_STOCK   = 10

# Default starter catalog for rich initial visualization
DEFAULT_INITIAL_MEDS = [
    {"medicine_id": "MED101", "medicine_name": "Paracetamol 500mg", "batch_number": "PCM-2026-A1", "quantity": "8", "expiry_date": "2026-10-10", "price": "20.00"},
    {"medicine_id": "MED102", "medicine_name": "Amoxicillin 250mg", "batch_number": "AMX-2026-B4", "quantity": "45", "expiry_date": "2026-11-05", "price": "65.50"},
    {"medicine_id": "MED103", "medicine_name": "Cetirizine 10mg",   "batch_number": "CET-2026-C2", "quantity": "90", "expiry_date": "2027-08-15", "price": "18.00"},
    {"medicine_id": "MED104", "medicine_name": "Azithromycin 500mg","batch_number": "AZI-2026-D9", "quantity": "5",  "expiry_date": "2027-04-20", "price": "115.00"},
    {"medicine_id": "MED105", "medicine_name": "Metformin 500mg",   "batch_number": "MET-2026-E3", "quantity": "120","expiry_date": "2027-12-31", "price": "35.00"},
    {"medicine_id": "MED106", "medicine_name": "Omeprazole 20mg",   "batch_number": "OMP-2026-F1", "quantity": "60", "expiry_date": "2026-11-12", "price": "42.00"},
]
DEFAULT_INITIAL_SUPS = [
    {"medicine_id": "MED101", "supplier_name": "Apex Healthcare Ltd",   "contact_number": "+91 9822012345", "email": "supply@apexpharma.com"},
    {"medicine_id": "MED102", "supplier_name": "Sun Bio Remedies",      "contact_number": "+91 9845098765", "email": "orders@sunbio.in"},
    {"medicine_id": "MED103", "supplier_name": "Cipla Distribution Hub","contact_number": "+91 9811234567", "email": "orders@ciplahub.com"},
    {"medicine_id": "MED104", "supplier_name": "Zydus Lifesciences",    "contact_number": "+91 9765432109", "email": "sales@zyduslife.com"},
    {"medicine_id": "MED105", "supplier_name": "Torrent Pharmaceuticals","contact_number": "+91 9923456781", "email": "dispatch@torrentpharma.com"},
    {"medicine_id": "MED106", "supplier_name": "Lupin Healthcare",      "contact_number": "+91 9890123456", "email": "support@lupin.com"},
]

# ─────────────────────────────────────────────
# Email Config — set these on Render as environment variables
# ─────────────────────────────────────────────
SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_CONFIGURED = bool(SMTP_EMAIL and SMTP_PASSWORD)

pending_registrations = {}
# Login OTPs live here, never in the session cookie the browser receives
pending_logins = {}

# ─────────────────────────────────────────────
# Per-User File Paths
# ─────────────────────────────────────────────
def user_dir(username):
    d = os.path.join(DATA_DIR, username.lower())
    os.makedirs(d, exist_ok=True)
    return d

def ufile(username, name):
    return os.path.join(user_dir(username), name)

def csv_file(u):   return ufile(u, "medicines.csv")
def sup_file(u):   return ufile(u, "suppliers.csv")
def rest_file(u):  return ufile(u, "restock_log.csv")
def usage_file(u): return ufile(u, "usage_log.csv")

# ─────────────────────────────────────────────
# CSV Helpers
# ─────────────────────────────────────────────
def load(path, fields):
    if not os.path.exists(path): return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def save(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

def _append_log(path, fields, entry):
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerow(entry)

# Shorthand for current user's files with auto-seeding
def medicines():
    med_path = csv_file(current_user.username)
    if not os.path.exists(med_path):
        save(med_path, FIELDNAMES, DEFAULT_INITIAL_MEDS)
        sup_path = sup_file(current_user.username)
        if not os.path.exists(sup_path):
            save(sup_path, SUPPLIER_FIELDS, DEFAULT_INITIAL_SUPS)
    data = load(med_path, FIELDNAMES)
    if not data and current_user.username.lower() in ("admin", "arpita"):
        save(med_path, FIELDNAMES, DEFAULT_INITIAL_MEDS)
        return DEFAULT_INITIAL_MEDS
    return data

def suppliers():   return load(sup_file(current_user.username),  SUPPLIER_FIELDS)
def restock_log(): return load(rest_file(current_user.username), RESTOCK_FIELDS)
def usage_log():   return load(usage_file(current_user.username),USAGE_FIELDS)
def get_users():   return load(USERS_FILE, USER_FIELDS)

def sup_map():
    return {s["medicine_id"].lower(): s for s in suppliers()}

def enrich(meds):
    sm    = sup_map()
    today = date.today()
    for m in meds:
        try:
            exp  = datetime.strptime(m["expiry_date"], DATE_FORMAT).date()
            days = (exp - today).days
        except Exception:
            days = 999
        m["days_left"] = days
        m["status"]    = "expired" if days < 0 else ("expiring" if days <= 30 else "ok")
        try:
            qty = int(m.get("quantity", 0))
        except (ValueError, TypeError):
            qty = 0
        try:
            price = float(m.get("price", 0))
        except (ValueError, TypeError):
            price = 0.0
        m["low_stock"]   = qty <= MIN_STOCK
        m["stock_value"] = round(price * qty, 2)
        s = sm.get(m["medicine_id"].lower(), {})
        m["supplier_name"]   = s.get("supplier_name",   "—")
        m["contact_number"]  = s.get("contact_number",  "—")
        m["supplier_email"]  = s.get("email",           "—")
    return meds

# ─────────────────────────────────────────────
# User Model
# ─────────────────────────────────────────────
class User(UserMixin):
    def __init__(self, username, password, mobile, email, role):
        self.id       = username
        self.username = username
        self.password = password
        self.mobile   = mobile
        self.email    = email
        self.role     = role

def find_user(username):
    for u in get_users():
        if u["username"].strip().lower() == username.strip().lower():
            return User(**u)
    return None

@login_manager.user_loader
def load_user(user_id):
    return find_user(user_id)

# ─────────────────────────────────────────────
# OTP / Email Helpers
# ─────────────────────────────────────────────
def generate_otp():
    return str(secrets.randbelow(900000) + 100000)

def send_email(to_email, subject, html):
    if not EMAIL_CONFIGURED:
        return False, "SMTP_EMAIL / SMTP_PASSWORD environment variables are not set"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_EMAIL
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.ehlo(); s.starttls()
            s.login(SMTP_EMAIL, SMTP_PASSWORD)
            s.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)

def send_otp_email(to_email, otp, username, mobile):
    html = f"""
    <html><body style="font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding:20px; background-color:#f8fafc;">
    <div style="max-width:500px; margin:auto; background:#ffffff; border-radius:16px; border:1px solid #e2e8f0; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">
      <div style="background:linear-gradient(135deg, #0284c7 0%, #0369a1 100%); padding:25px 30px; text-align:center; color:#ffffff;">
        <h2 style="margin:0; font-size:24px; font-weight:700;">MediAlert Pro</h2>
        <p style="margin:5px 0 0; font-size:14px; opacity:0.85;">Clinical Medicine Inventory &amp; Alert System</p>
      </div>
      <div style="padding:30px;">
        <p style="font-size:16px; color:#334155; margin-top:0;">Hello <strong>{username}</strong>,</p>
        <p style="font-size:14px; color:#64748b; line-height:1.5;">Your one-time security verification code (OTP) is:</p>
        <div style="background:#f0f9ff; border:2px dashed #0284c7; border-radius:12px; padding:18px; text-align:center; margin:25px 0;">
          <span style="font-size:34px; font-weight:800; letter-spacing:10px; color:#0369a1; font-family:monospace;">{otp}</span>
        </div>
        <p style="font-size:13px; color:#94a3b8; margin-bottom:0;">This verification code is valid for 5 minutes. If you did not request this, please ignore this email.</p>
      </div>
      <div style="background:#f8fafc; padding:15px; text-align:center; border-top:1px solid #e2e8f0; font-size:12px; color:#94a3b8;">
        Automated Security Dispatch &bull; MediAlert Pro Clinical Pharmacy System
      </div>
    </div></body></html>"""
    ok, err = send_email(to_email, "MediAlert - Your Verification OTP Code", html)
    if not ok:
        print(f"\n[EMAIL ERROR] Failed to send the verification code to {to_email}: {err}")
    else:
        print(f"\n[EMAIL SUCCESS] OTP email successfully dispatched to: {to_email}\n")
    return ok, err

def dispatch_otp(to_email, otp, username, mobile):
    threading.Thread(target=send_otp_email, args=(to_email, otp, username, mobile), daemon=True).start()
    if EMAIL_CONFIGURED:
        flash("A 6-digit security code has been emailed to your registered address.", "info")
    else:
        flash("No code was emailed: SMTP_EMAIL / SMTP_PASSWORD are not set on this server.", "warning")

# ─────────────────────────────────────────────
# Context Processor
# ─────────────────────────────────────────────
@app.context_processor
def inject_global_alerts():
    if not current_user.is_authenticated:
        return dict(
            g_expired=[], g_expiring=[], g_low=[],
            g_total=0, g_value=0, g_alert_count=0,
            now=datetime.now(), all_users=get_users()
        )
    try:
        meds     = enrich(medicines())
        expired  = [m for m in meds if m["status"] == "expired"]
        expiring = [m for m in meds if m["status"] == "expiring"]
        low      = [m for m in meds if m["low_stock"] and m["status"] != "expired"]
        total_val = sum(float(m.get("price",0)) * int(m.get("quantity",0)) for m in meds)
        total_count = len(meds)
        alert_count = len(expired) + len(expiring) + len(low)
        return dict(
            g_expired=expired,
            g_expiring=expiring,
            g_low=low,
            g_total=total_count,
            g_value=total_val,
            g_alert_count=alert_count,
            now=datetime.now(),
            all_users=get_users()
        )
    except Exception:
        return dict(
            g_expired=[], g_expiring=[], g_low=[],
            g_total=0, g_value=0, g_alert_count=0,
            now=datetime.now(), all_users=get_users()
        )

# ─────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────
@app.route("/demo-login/<username>")
def demo_login(username):
    """1-Click Quick Demo Login for instant testing without 2FA delays."""
    user = find_user(username)
    if user:
        login_user(user, remember=True)
        flash(f"⚡ Logged in successfully as {user.username} ({user.role})!", "success")
        return redirect(url_for("index"))
    flash(f"User '{username}' not found.", "danger")
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET","POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        confirm  = request.form.get("confirm_password","").strip()
        mobile   = request.form.get("mobile","").strip()
        email    = request.form.get("email","").strip().lower()

        if not all([username, password, confirm, mobile, email]):
            flash("All fields are required.", "danger"); return redirect(url_for("signup"))
        if password != confirm:
            flash("Passwords do not match.", "danger"); return redirect(url_for("signup"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger"); return redirect(url_for("signup"))
        if not mobile.isdigit() or len(mobile) != 10:
            flash("Enter a valid 10-digit mobile number.", "danger"); return redirect(url_for("signup"))

        users = get_users()
        if any(u["username"].lower() == username.lower() for u in users):
            flash("Username already taken. Please choose another username.", "danger")
            return redirect(url_for("signup"))
        if any(u["email"].lower() == email for u in users):
            flash("Email already registered. Please login.", "danger")
            return redirect(url_for("signup"))

        otp = generate_otp()
        pending_registrations[email] = {
            "username": username, "password": password,
            "mobile": mobile, "email": email, "role": "user",
            "otp": otp, "otp_time": datetime.now().strftime(TS_FORMAT),
        }
        dispatch_otp(email, otp, username, mobile)
        session["signup_email"] = email
        return redirect(url_for("verify_signup_otp"))
    return render_template("signup.html")


@app.route("/verify-signup", methods=["GET","POST"])
def verify_signup_otp():
    email = session.get("signup_email")
    if not email or email not in pending_registrations:
        flash("Registration session expired. Please sign up again.", "danger")
        return redirect(url_for("signup"))
    pending = pending_registrations[email]
    if request.method == "POST":
        entered  = request.form.get("otp","").strip()
        otp_time = datetime.strptime(pending["otp_time"], TS_FORMAT)
        if (datetime.now() - otp_time).seconds > 300:
            pending_registrations.pop(email, None); session.pop("signup_email", None)
            flash("OTP expired. Please sign up again.", "danger")
            return redirect(url_for("signup"))
        if entered == pending["otp"]:
            users = get_users()
            users.append({k: pending[k] for k in USER_FIELDS})
            save(USERS_FILE, USER_FIELDS, users)
            # Create and initialize user's permanent isolated data store
            udir = user_dir(pending["username"])
            user_med_file = os.path.join(udir, "medicines.csv")
            if not os.path.exists(user_med_file):
                save(user_med_file, FIELDNAMES, DEFAULT_INITIAL_MEDS)
            user_sup_file = os.path.join(udir, "suppliers.csv")
            if not os.path.exists(user_sup_file):
                save(user_sup_file, SUPPLIER_FIELDS, DEFAULT_INITIAL_SUPS)
            reg_username = pending["username"]
            pending_registrations.pop(email, None); session.pop("signup_email", None)
            flash(f"Account successfully registered and saved! Welcome, {reg_username}. Please login.", "success")
            return redirect(url_for("login"))
        else:
            flash("Incorrect OTP entered. Please check your email and try again.", "danger")
    masked = email[:4] + "***@" + email.split("@")[-1]
    return render_template("verify_signup_otp.html", masked_email=masked)


@app.route("/resend-signup-otp")
def resend_signup_otp():
    email = session.get("signup_email")
    if not email or email not in pending_registrations:
        return redirect(url_for("signup"))
    otp = generate_otp()
    pending_registrations[email].update({"otp": otp, "otp_time": datetime.now().strftime(TS_FORMAT)})
    dispatch_otp(email, otp, pending_registrations[email]["username"], pending_registrations[email]["mobile"])
    return redirect(url_for("verify_signup_otp"))


@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        mobile   = request.form.get("mobile","").strip()
        user     = find_user(username)
        if not user or user.password != password:
            flash("Invalid username or password.", "danger"); return redirect(url_for("login"))
        if user.mobile.strip() != mobile:
            flash("Registered mobile number does not match account.", "danger"); return redirect(url_for("login"))
        otp = generate_otp()
        pending_logins[user.username] = {"otp": otp, "time": datetime.now().strftime(TS_FORMAT)}
        session["otp_username"] = user.username
        dispatch_otp(user.email, otp, user.username, user.mobile)
        return redirect(url_for("verify_otp"))
    return render_template("login.html")


@app.route("/verify-otp", methods=["GET","POST"])
def verify_otp():
    username = session.get("otp_username")
    if not username or username not in pending_logins:
        return redirect(url_for("login"))
    pending = pending_logins[username]
    if request.method == "POST":
        entered  = request.form.get("otp","").strip()
        otp_time = datetime.strptime(pending["time"], TS_FORMAT)
        if (datetime.now() - otp_time).seconds > 300:
            pending_logins.pop(username, None); session.pop("otp_username", None)
            flash("OTP expired. Login again.", "danger"); return redirect(url_for("login"))
        if entered == pending["otp"]:
            pending_logins.pop(username, None)
            user = find_user(session.pop("otp_username"))
            login_user(user, remember=True)
            flash(f"Welcome back, {user.username}! Access granted.", "success")
            return redirect(url_for("index"))
        flash("Incorrect OTP entered. Please try again.", "danger")
    user = find_user(username)
    masked = (user.email[:4] + "***@" + user.email.split("@")[-1]) if user else ""
    return render_template("verify_otp.html", masked_email=masked)


@app.route("/resend-otp")
def resend_otp():
    username = session.get("otp_username")
    if not username or username not in pending_logins:
        return redirect(url_for("login"))
    user = find_user(username)
    if not user: return redirect(url_for("login"))
    otp = generate_otp()
    pending_logins[username] = {"otp": otp, "time": datetime.now().strftime(TS_FORMAT)}
    dispatch_otp(user.email, otp, user.username, user.mobile)
    return redirect(url_for("verify_otp"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ─────────────────────────────────────────────
# Main Routes — per-user data
# ─────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    meds  = enrich(medicines())
    stats = {
        "total":    len(meds),
        "units":    sum(int(m.get("quantity", 0)) for m in meds),
        "expired":  sum(1 for m in meds if m["status"] == "expired"),
        "expiring": sum(1 for m in meds if m["status"] == "expiring"),
        "low":      sum(1 for m in meds if m["low_stock"]),
        "value":    sum(float(m.get("price", 0)) * int(m.get("quantity", 0)) for m in meds),
    }
    return render_template("index.html", meds=meds, stats=stats, today=date.today())


@app.route("/add", methods=["GET","POST"])
@login_required
def add():
    u = current_user.username
    if request.method == "POST":
        meds = medicines()
        mid  = request.form["medicine_id"].strip()
        if any(m["medicine_id"].lower() == mid.lower() for m in meds):
            flash(f"Medicine ID '{mid}' already exists.", "danger")
            return redirect(url_for("add"))
        meds.append({
            "medicine_id":   mid,
            "medicine_name": request.form["medicine_name"].strip(),
            "batch_number":  request.form["batch_number"].strip(),
            "quantity":      request.form["quantity"].strip(),
            "expiry_date":   request.form["expiry_date"].strip(),
            "price":         request.form["price"].strip(),
        })
        save(csv_file(u), FIELDNAMES, meds)
        sname = request.form.get("supplier_name","").strip()
        if sname:
            sups = load(sup_file(u), SUPPLIER_FIELDS)
            sups = [s for s in sups if s["medicine_id"].lower() != mid.lower()]
            sups.append({"medicine_id": mid, "supplier_name": sname,
                         "contact_number": request.form.get("contact_number","").strip(),
                         "email": request.form.get("email","").strip()})
            save(sup_file(u), SUPPLIER_FIELDS, sups)
        flash(f"Medicine '{request.form['medicine_name']}' added!", "success")
        return redirect(url_for("index"))
    return render_template("add.html")


@app.route("/edit/<med_id>", methods=["GET","POST"])
@login_required
def edit(med_id):
    u    = current_user.username
    meds = medicines()
    target = next((m for m in meds if m["medicine_id"].lower() == med_id.lower()), None)
    if not target:
        flash("Medicine not found.", "danger"); return redirect(url_for("index"))
    sup = {s["medicine_id"].lower(): s for s in load(sup_file(u), SUPPLIER_FIELDS)}.get(med_id.lower(), {})
    if request.method == "POST":
        old_qty    = int(target["quantity"])
        changed_by = request.form.get("changed_by", u).strip() or u
        target["quantity"]    = request.form["quantity"].strip()
        target["price"]       = request.form["price"].strip()
        target["expiry_date"] = request.form["expiry_date"].strip()
        save(csv_file(u), FIELDNAMES, meds)
        if int(target["quantity"]) != old_qty:
            _append_log(rest_file(u), RESTOCK_FIELDS, {
                "timestamp": datetime.now().strftime(TS_FORMAT),
                "medicine_id": target["medicine_id"], "medicine_name": target["medicine_name"],
                "old_quantity": old_qty, "new_quantity": int(target["quantity"]), "changed_by": changed_by,
            })
        sname = request.form.get("supplier_name","").strip()
        if sname:
            sups = load(sup_file(u), SUPPLIER_FIELDS)
            sups = [s for s in sups if s["medicine_id"].lower() != med_id.lower()]
            sups.append({"medicine_id": med_id, "supplier_name": sname,
                         "contact_number": request.form.get("contact_number","").strip(),
                         "email": request.form.get("email","").strip()})
            save(sup_file(u), SUPPLIER_FIELDS, sups)
        flash(f"'{target['medicine_name']}' updated.", "success")
        return redirect(url_for("index"))
    return render_template("edit.html", med=target, sup=sup)


@app.route("/dispense/<med_id>", methods=["GET","POST"])
@login_required
def dispense(med_id):
    u    = current_user.username
    meds = medicines()
    target = next((m for m in meds if m["medicine_id"].lower() == med_id.lower()), None)
    if not target:
        flash("Medicine not found.", "danger"); return redirect(url_for("index"))
    if request.method == "POST":
        qty_str = request.form.get("qty_used","").strip()
        by      = request.form.get("dispensed_by", u).strip() or u
        note    = request.form.get("note","").strip()
        if not qty_str.isdigit() or int(qty_str) <= 0:
            flash("Enter a valid quantity.", "danger"); return redirect(url_for("dispense", med_id=med_id))
        qty_used   = int(qty_str)
        qty_before = int(target["quantity"])
        if qty_used > qty_before:
            flash(f"Only {qty_before} in stock.", "danger"); return redirect(url_for("dispense", med_id=med_id))
        qty_after = qty_before - qty_used
        target["quantity"] = qty_after
        save(csv_file(u), FIELDNAMES, meds)
        _append_log(usage_file(u), USAGE_FIELDS, {
            "timestamp": datetime.now().strftime(TS_FORMAT),
            "medicine_id": target["medicine_id"], "medicine_name": target["medicine_name"],
            "qty_used": qty_used, "qty_before": qty_before, "qty_after": qty_after,
            "dispensed_by": by, "note": note,
        })
        flash(f"Dispensed {qty_used} of '{target['medicine_name']}'. Remaining: {qty_after}."
              + (" Low stock!" if qty_after <= MIN_STOCK else ""),
              "success" if qty_after > MIN_STOCK else "warning")
        return redirect(url_for("index"))
    return render_template("dispense.html", med=enrich([target])[0])


@app.route("/quick-restock/<med_id>", methods=["POST"])
@login_required
def quick_restock(med_id):
    u = current_user.username
    meds = medicines()
    target = next((m for m in meds if m["medicine_id"].lower() == med_id.lower()), None)
    if not target:
        flash("Medicine not found.", "danger")
        return redirect(url_for("index"))
    
    add_qty_str = request.form.get("add_quantity", "").strip()
    by = request.form.get("changed_by", u).strip() or u
    new_expiry = request.form.get("new_expiry", "").strip()
    
    if not add_qty_str.isdigit() or int(add_qty_str) <= 0:
        flash("Please enter a valid positive number for restock quantity.", "danger")
        return redirect(url_for("index"))
        
    add_qty = int(add_qty_str)
    old_qty = int(target["quantity"])
    new_qty = old_qty + add_qty
    target["quantity"] = str(new_qty)
    
    if new_expiry:
        try:
            datetime.strptime(new_expiry, DATE_FORMAT)
            target["expiry_date"] = new_expiry
        except ValueError:
            pass

    save(csv_file(u), FIELDNAMES, meds)
    _append_log(rest_file(u), RESTOCK_FIELDS, {
        "timestamp": datetime.now().strftime(TS_FORMAT),
        "medicine_id": target["medicine_id"],
        "medicine_name": target["medicine_name"],
        "old_quantity": old_qty,
        "new_quantity": new_qty,
        "changed_by": by,
    })
    flash(f"✅ Restocked +{add_qty} units of '{target['medicine_name']}'. Current stock: {new_qty}.", "success")
    return redirect(url_for("index"))


@app.route("/quick-dispense/<med_id>", methods=["POST"])
@login_required
def quick_dispense(med_id):
    u = current_user.username
    meds = medicines()
    target = next((m for m in meds if m["medicine_id"].lower() == med_id.lower()), None)
    if not target:
        flash("Medicine not found.", "danger")
        return redirect(url_for("index"))

    qty_str = request.form.get("qty_used","").strip()
    by = request.form.get("dispensed_by", u).strip() or u
    note = request.form.get("note","").strip()

    if not qty_str.isdigit() or int(qty_str) <= 0:
        flash("Enter a valid quantity to dispense.", "danger")
        return redirect(url_for("index"))

    qty_used = int(qty_str)
    qty_before = int(target["quantity"])
    if qty_used > qty_before:
        flash(f"Insufficient stock! Available: {qty_before}, requested: {qty_used}.", "danger")
        return redirect(url_for("index"))

    qty_after = qty_before - qty_used
    target["quantity"] = str(qty_after)
    save(csv_file(u), FIELDNAMES, meds)
    _append_log(usage_file(u), USAGE_FIELDS, {
        "timestamp": datetime.now().strftime(TS_FORMAT),
        "medicine_id": target["medicine_id"],
        "medicine_name": target["medicine_name"],
        "qty_used": qty_used,
        "qty_before": qty_before,
        "qty_after": qty_after,
        "dispensed_by": by,
        "note": note,
    })
    flash(f"💊 Dispensed {qty_used} of '{target['medicine_name']}'. Remaining: {qty_after}."
          + (" ⚠ Running low!" if qty_after <= MIN_STOCK else ""),
          "success" if qty_after > MIN_STOCK else "warning")
    return redirect(url_for("index"))


@app.route("/export-csv")
@login_required
def export_csv():
    u = current_user.username
    meds = enrich(medicines())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "medicine_id","medicine_name","batch_number","quantity",
        "expiry_date","price","stock_value","status","days_left",
        "supplier_name","contact_number","supplier_email"
    ])
    writer.writeheader()
    for m in meds:
        writer.writerow({
            "medicine_id": m.get("medicine_id", ""),
            "medicine_name": m.get("medicine_name", ""),
            "batch_number": m.get("batch_number", ""),
            "quantity": m.get("quantity", ""),
            "expiry_date": m.get("expiry_date", ""),
            "price": m.get("price", ""),
            "stock_value": m.get("stock_value", ""),
            "status": m.get("status", ""),
            "days_left": m.get("days_left", ""),
            "supplier_name": m.get("supplier_name", ""),
            "contact_number": m.get("contact_number", ""),
            "supplier_email": m.get("supplier_email", "")
        })
    filename = f"medialert_inventory_{u}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


@app.route("/import-csv", methods=["POST"])
@login_required
def import_csv():
    u = current_user.username
    file = request.files.get("csv_file")
    if not file or file.filename == "":
        flash("Please choose a valid CSV file to upload.", "danger")
        return redirect(url_for("index"))
    try:
        content = file.stream.read().decode("utf-8-sig")
        reader = csv.DictReader(content.splitlines())
        current_meds = medicines()
        med_map = {m["medicine_id"].lower(): m for m in current_meds}
        added_count = 0
        updated_count = 0

        for row in reader:
            mid = row.get("medicine_id", "").strip()
            mname = row.get("medicine_name", "").strip()
            batch = row.get("batch_number", "").strip() or "BT-IMPORT"
            qty = row.get("quantity", "").strip() or "10"
            exp = row.get("expiry_date", "").strip() or date.today().strftime(DATE_FORMAT)
            price = row.get("price", "").strip() or "10.0"

            if not mid or not mname:
                continue

            if mid.lower() in med_map:
                med_map[mid.lower()]["quantity"] = qty
                med_map[mid.lower()]["price"] = price
                med_map[mid.lower()]["expiry_date"] = exp
                updated_count += 1
            else:
                med_map[mid.lower()] = {
                    "medicine_id": mid, "medicine_name": mname, "batch_number": batch,
                    "quantity": qty, "expiry_date": exp, "price": price
                }
                added_count += 1

        save(csv_file(u), FIELDNAMES, list(med_map.values()))
        flash(f"CSV Import Complete! Added {added_count} new, updated {updated_count} medicines.", "success")
    except Exception as e:
        flash(f"Error importing CSV: {e}", "danger")
    return redirect(url_for("index"))


@app.route("/delete/<med_id>", methods=["POST"])
@login_required
def delete(med_id):
    u = current_user.username
    meds = [m for m in medicines() if m["medicine_id"].lower() != med_id.lower()]
    save(csv_file(u), FIELDNAMES, meds)
    sups = [s for s in load(sup_file(u), SUPPLIER_FIELDS) if s["medicine_id"].lower() != med_id.lower()]
    save(sup_file(u), SUPPLIER_FIELDS, sups)
    flash("Medicine deleted.", "warning"); return redirect(url_for("index"))


@app.route("/alerts")
@login_required
def alerts():
    meds = enrich(medicines())
    return render_template("alerts.html",
        expired  = [m for m in meds if m["status"] == "expired"],
        expiring = [m for m in meds if m["status"] == "expiring"],
        low      = [m for m in meds if m["low_stock"]])


@app.route("/report")
@login_required
def report():
    meds  = enrich(medicines())
    stats = {
        "total":    len(meds),
        "expired":  sum(1 for m in meds if m["status"] == "expired"),
        "expiring": sum(1 for m in meds if m["status"] == "expiring"),
        "low":      sum(1 for m in meds if m["low_stock"]),
        "value":    sum(float(m["price"]) * int(m["quantity"]) for m in meds),
    }
    return render_template("report.html", meds=meds, stats=stats,
                           log=restock_log(), ulog=usage_log(), today=date.today())


@app.route("/usage")
@login_required
def usage():
    return render_template("usage.html", log=list(reversed(usage_log())))


@app.route("/search")
@login_required
def search():
    q    = request.args.get("q","").strip().lower()
    meds = enrich(medicines()) if q else []
    if q:
        meds = [m for m in meds if q in m["medicine_id"].lower() or q in m["medicine_name"].lower()]
    return render_template("search.html", meds=meds, q=q)

# ─────────────────────────────────────────────
# Daily Alert Email
# ─────────────────────────────────────────────
def send_expiry_alert_email_for(username, user_email):
    """Send daily alert for a specific user's medicines."""
    meds     = enrich(load(csv_file(username), FIELDNAMES))
    today    = date.today()
    expired  = [m for m in meds if m["status"] == "expired"]
    expiring = [m for m in meds if m["status"] == "expiring"]
    low      = [m for m in meds if m["low_stock"] and m["status"] != "expired"]

    if not expired and not expiring and not low:
        return

    def tbl(lst, bg, hdr_color, cols, row_fn):
        ths = "".join(f'<th style="padding:10px 12px;text-align:left;">{c}</th>' for c in cols)
        rows = "".join(row_fn(m) for m in lst)
        return f"""<table style="width:100%;border-collapse:collapse;margin-top:8px;">
          <thead><tr style="background:{hdr_color};color:#fff;">{ths}</tr></thead>
          <tbody style="background:{bg};">{rows}</tbody></table>"""

    def exp_row(m):
        return (f'<tr><td style="padding:8px 12px;">{m["medicine_id"]}</td>'
                f'<td style="padding:8px 12px;">{m["medicine_name"]}</td>'
                f'<td style="padding:8px 12px;color:#dc3545;font-weight:bold;">{m["expiry_date"]}</td>'
                f'<td style="padding:8px 12px;">{m["quantity"]}</td></tr>')

    def low_row(m):
        return (f'<tr><td style="padding:8px 12px;">{m["medicine_id"]}</td>'
                f'<td style="padding:8px 12px;">{m["medicine_name"]}</td>'
                f'<td style="padding:8px 12px;color:#856404;font-weight:bold;">{m["quantity"]}</td>'
                f'<td style="padding:8px 12px;">{m["expiry_date"]}</td></tr>')

    sections = ""
    if expired:
        sections += f"<h3 style='color:#dc3545;'>❌ Expired ({len(expired)})</h3>"
        sections += tbl(expired,"#fff8f8","#dc3545",["ID","Name","Expiry","Qty"], exp_row)
    if expiring:
        sections += f"<h3 style='color:#fd7e14;margin-top:20px;'>⚠ Expiring Soon ({len(expiring)})</h3>"
        sections += tbl(expiring,"#fffaf5","#fd7e14",["ID","Name","Expiry","Qty"], exp_row)
    if low:
        sections += f"<h3 style='color:#856404;margin-top:20px;'>📦 Low Stock ({len(low)})</h3>"
        sections += tbl(low,"#fffdf0","#ffc107",["ID","Name","Stock","Expiry"], low_row)

    html = f"""<html><body style="font-family:'Segoe UI',sans-serif;background:#f0f4f8;padding:20px;">
    <div style="max-width:660px;margin:auto;background:#fff;border-radius:12px;
                box-shadow:0 4px 20px rgba(0,0,0,.1);overflow:hidden;">
      <div style="background:linear-gradient(135deg,#1a3c5e,#0d2137);padding:24px 28px;color:#fff;">
        <h2 style="margin:0;">💊 MediAlert — Daily Report</h2>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.7);">{today.strftime('%d %B %Y')} | User: {username}</p>
      </div>
      <div style="padding:20px 28px;">
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
          <div style="flex:1;min-width:100px;background:#fff8f8;border-top:3px solid #dc3545;
                      border-radius:8px;padding:14px;text-align:center;">
            <div style="font-size:1.8rem;font-weight:700;color:#dc3545;">{len(expired)}</div>
            <div style="color:#888;font-size:.82rem;">Expired</div>
          </div>
          <div style="flex:1;min-width:100px;background:#fffaf5;border-top:3px solid #fd7e14;
                      border-radius:8px;padding:14px;text-align:center;">
            <div style="font-size:1.8rem;font-weight:700;color:#fd7e14;">{len(expiring)}</div>
            <div style="color:#888;font-size:.82rem;">Expiring Soon</div>
          </div>
          <div style="flex:1;min-width:100px;background:#fffdf0;border-top:3px solid #ffc107;
                      border-radius:8px;padding:14px;text-align:center;">
            <div style="font-size:1.8rem;font-weight:700;color:#856404;">{len(low)}</div>
            <div style="color:#888;font-size:.82rem;">Low Stock</div>
          </div>
        </div>
        {sections}
      </div>
      <div style="background:#f8fafc;padding:14px 28px;text-align:center;
                  color:#aaa;font-size:.8rem;border-top:1px solid #eee;">
        Automated daily alert — MediAlert System
      </div>
    </div></body></html>"""

    subj = f"MediAlert Daily Report {today.strftime('%d %b %Y')} — {len(expired)} Expired, {len(expiring)} Expiring"
    ok, err = send_email(user_email, subj, html)
    if ok:
        print(f"[Scheduler] Alert sent to {user_email} for user '{username}'")
    else:
        print(f"[Scheduler] Failed for '{username}': {err}")


def daily_alert_job():
    """Run every day — send alert email to every registered user."""
    for u in get_users():
        try:
            send_expiry_alert_email_for(u["username"], u["email"])
        except Exception as e:
            print(f"[Scheduler] Error for {u['username']}: {e}")


@app.route("/send-alert-now")
@login_required
def send_alert_now():
    send_expiry_alert_email_for(current_user.username, current_user.email)
    flash(f"Alert email sent to {current_user.email}!", "success")
    return redirect(url_for("index"))


# ─────────────────────────────────────────────
# Admin Panel
# ─────────────────────────────────────────────
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    users = get_users()
    user_stats = []
    for u in users:
        meds = enrich(load(csv_file(u["username"]), FIELDNAMES))
        user_stats.append({
            "username":  u["username"],
            "email":     u["email"],
            "mobile":    u["mobile"],
            "role":      u["role"],
            "total":     len(meds),
            "expired":   sum(1 for m in meds if m["status"] == "expired"),
            "expiring":  sum(1 for m in meds if m["status"] == "expiring"),
            "low":       sum(1 for m in meds if m["low_stock"]),
            "value":     sum(float(m["price"]) * int(m["quantity"]) for m in meds),
        })
    return render_template("admin.html", users=user_stats, total_users=len(users))


@app.route("/admin/view/<username>")
@login_required
@admin_required
def admin_view_user(username):
    user = find_user(username)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_panel"))
    meds = enrich(load(csv_file(username), FIELDNAMES))
    stats = {
        "total":    len(meds),
        "expired":  sum(1 for m in meds if m["status"] == "expired"),
        "expiring": sum(1 for m in meds if m["status"] == "expiring"),
        "low":      sum(1 for m in meds if m["low_stock"]),
        "value":    sum(float(m["price"]) * int(m["quantity"]) for m in meds),
    }
    return render_template("admin_user.html", user=user, meds=meds, stats=stats)


@app.route("/admin/delete-user/<username>", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(username):
    if username.lower() == "admin":
        flash("Cannot delete admin account.", "danger")
        return redirect(url_for("admin_panel"))
    users = [u for u in get_users() if u["username"].lower() != username.lower()]
    save(USERS_FILE, USER_FIELDS, users)
    # Remove user's data folder
    import shutil
    udir = user_dir(username)
    if os.path.exists(udir):
        shutil.rmtree(udir)
    flash(f"User '{username}' deleted successfully.", "warning")
    return redirect(url_for("admin_panel"))


@app.route("/admin/change-role/<username>", methods=["POST"])
@login_required
@admin_required
def admin_change_role(username):
    new_role = request.form.get("role", "user")
    users = get_users()
    for u in users:
        if u["username"].lower() == username.lower():
            u["role"] = new_role
            break
    save(USERS_FILE, USER_FIELDS, users)
    flash(f"Role updated for '{username}'.", "success")
    return redirect(url_for("admin_panel"))


# ─────────────────────────────────────────────
# Scheduler — daily 9 AM
# ─────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.add_job(daily_alert_job, trigger="cron", hour=9, minute=0,
                  id="daily_alert", replace_existing=True)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
