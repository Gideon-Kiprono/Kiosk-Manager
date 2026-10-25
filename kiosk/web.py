"""Flask web app. Thin layer: read the form, call services, show the result."""

import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request,
                   session, url_for)

from kiosk import auth, chart, services
from kiosk.db import get_connection, init_db
from kiosk.labels import SW, error_text
from kiosk.services import KioskError

NAIROBI_HOURS = 3
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60


def create_app(db_path=None, testing=False):
    app = Flask(__name__)
    app.config.update(
        # Without SECRET_KEY set, a random key is used: fine for local work, but
        # everyone is logged out whenever the server restarts. Set it in production.
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DB_PATH=db_path or os.environ.get("DB_PATH", "kiosk.db"),
        TESTING=testing,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",   # set to 1 behind HTTPS
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    )

    setup = get_connection(app.config["DB_PATH"])
    init_db(setup)
    setup.close()

    failed_logins = {}      # email -> [timestamps]; in memory, resets on restart

    # ---------- per-request plumbing ----------

    def db():
        if "db" not in g:
            g.db = get_connection(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        if "uid" in session:
            g.user = auth.get_user(db(), session["uid"])
            if g.user is None:
                session.clear()

        if request.method == "POST":
            sent = request.form.get("csrf_token", "")
            expected = session.get("csrf", "")
            if not expected or not hmac.compare_digest(sent, expected):
                flash(SW["err_csrf"], "error")
                return redirect(request.referrer or url_for("login"))

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'")
        return resp

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    @app.context_processor
    def inject_globals():
        return {"t": SW, "user": g.get("user"), "csrf_token": csrf_token}

    @app.template_filter("kes")
    def kes(value):
        return f"{value:,}"

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def start_session(user_id):
        session.clear()                     # new session on login: prevents fixation
        session["uid"] = user_id
        session.permanent = True

    # ---------- accounts ----------

    @app.route("/ingia", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("home"))
        if request.method == "POST":
            email = auth.normalise_email(request.form.get("email", ""))
            now = time.time()
            recent = [ts for ts in failed_logins.get(email, []) if now - ts < LOCKOUT_SECONDS]
            failed_logins[email] = recent
            try:
                if len(recent) >= MAX_FAILED_LOGINS:
                    raise KioskError("too_many_attempts")
                user = auth.authenticate(db(), email, request.form.get("password", ""))
                failed_logins.pop(email, None)
                start_session(user["id"])
                flash(SW["welcome_user"].format(kiosk=user["kiosk_name"]), "ok")
                return redirect(url_for("home"))
            except KioskError as err:
                if err.code == "bad_login":
                    failed_logins[email].append(now)
                flash(error_text(err), "error")
                return redirect(url_for("login"))
        return render_template("login.html")

    @app.route("/jisajili", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("home"))
        if request.method == "POST":
            try:
                uid = auth.register(db(), request.form.get("email", ""),
                                    request.form.get("password", ""),
                                    request.form.get("kiosk_name", ""))
                start_session(uid)
                flash(SW["welcome_user"].format(
                    kiosk=auth.get_user(db(), uid)["kiosk_name"]), "ok")
                return redirect(url_for("home"))
            except KioskError as err:
                flash(error_text(err), "error")
                return redirect(url_for("register"))
        return render_template("register.html")

    @app.post("/demo")
    def demo():
        start_session(auth.create_demo(db()))
        flash(SW["welcome_user"].format(kiosk="Duka la Demo"), "ok")
        return redirect(url_for("home"))

    @app.post("/toka")
    def logout():
        session.clear()
        flash(SW["logged_out"], "ok")
        return redirect(url_for("login"))

    # ---------- the kiosk pages (all need a login) ----------

    def local_today():
        return datetime.now(timezone(timedelta(hours=NAIROBI_HOURS))).date().isoformat()

    @app.get("/")
    @login_required
    def home():
        days = services.daily_sales(db(), g.user["id"], local_today(), 7, NAIROBI_HOURS)
        return render_template(
            "home.html", days=days,
            today_revenue=days[-1]["revenue"], week_revenue=sum(d["revenue"] for d in days),
            chart_svg=chart.sales_bars(days, SW["chart_title"]),
            day_label=chart.day_label,
            low=services.low_stock(db(), g.user["id"]))

    @app.get("/stoo")
    @login_required
    def stock():
        q = request.args.get("q", "").strip()
        products = services.list_products(db(), g.user["id"])
        if q:
            try:
                products = services.search_products(db(), g.user["id"], q)
            except KioskError as err:
                flash(error_text(err), "error")
        return render_template("stock.html", products=products, q=q)

    @app.route("/bidhaa/<int:product_id>/hariri", methods=["GET", "POST"])
    @login_required
    def edit_product(product_id):
        product = services.get_product_by_id(db(), g.user["id"], product_id)
        if product is None:
            abort(404)
        if request.method == "POST":
            try:
                services.update_product(db(), g.user["id"], product_id,
                                        request.form.get("name", ""),
                                        request.form.get("price", ""),
                                        request.form.get("quantity", ""))
                flash(SW["saved_ok"], "ok")
                return redirect(url_for("stock"))
            except KioskError as err:
                flash(error_text(err), "error")
                return redirect(url_for("edit_product", product_id=product_id))
        return render_template("edit.html", p=product)

    @app.post("/bidhaa/<int:product_id>/futa")
    @login_required
    def delete_product(product_id):
        if not request.form.get("confirm"):
            return redirect(url_for("edit_product", product_id=product_id))
        try:
            removed = services.remove_product(db(), g.user["id"], product_id)
        except KioskError:
            abort(404)
        flash(SW["deleted_ok"].format(product=removed["name"]), "ok")
        return redirect(url_for("stock"))

    @app.get("/zinaisha")
    @login_required
    def shopping_list():
        return render_template("shopping_list.html", low=services.low_stock(db(), g.user["id"]),
                               today=local_today())

    @app.route("/uza", methods=["GET", "POST"])
    @login_required
    def sell():
        if request.method == "POST":
            try:
                result = services.sell(db(), g.user["id"], request.form.get("product", ""),
                                       request.form.get("quantity", ""))
                flash(SW["sold_ok"].format(
                    quantity=result["quantity"], product=result["product"],
                    total=f"{result['total']:,}"), "ok")
            except KioskError as err:
                flash(error_text(err), "error")
            return redirect(url_for("sell"))
        sellable = [p for p in services.list_products(db(), g.user["id"]) if p["quantity"] > 0]
        return render_template("sell.html", products=sellable)

    @app.route("/ongeza", methods=["GET", "POST"])
    @login_required
    def add():
        if request.method == "POST":
            price = request.form.get("price", "").strip() or None
            try:
                action, product = services.add_or_restock(
                    db(), g.user["id"], request.form.get("name", ""),
                    request.form.get("quantity", ""), price)
                msg = SW["restocked_ok"] if action == "restocked" else SW["added_ok"]
                flash(msg.format(product=product["name"], quantity=product["quantity"]), "ok")
            except KioskError as err:
                flash(error_text(err), "error")
            return redirect(url_for("add"))
        return render_template("add.html", products=services.list_products(db(), g.user["id"]),
                               prefill=request.args.get("bidhaa", "")[:60])

    @app.get("/ripoti")
    @login_required
    def report():
        period = request.args.get("period", "today")
        data = services.sales_report(
            db(), g.user["id"], date_from=local_today() if period == "today" else None,
            tz_hours=NAIROBI_HOURS)
        return render_template("report.html", r=data, period=period)

    @app.get("/ripoti.csv")
    @login_required
    def report_csv():
        period = request.args.get("period", "today")
        body = services.export_sales_csv(
            db(), g.user["id"], date_from=local_today() if period == "today" else None,
            tz_hours=NAIROBI_HOURS, header=SW["csv_header"])
        name = f"mauzo-{local_today()}.csv" if period == "today" else "mauzo-yote.csv"
        return Response(body, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return app
