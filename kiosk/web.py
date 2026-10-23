"""Flask web app. Thin layer: read the form, call services, show the result."""

import os
from datetime import datetime, timedelta, timezone

from flask import Flask, flash, g, redirect, render_template, request, url_for

from kiosk import services
from kiosk.db import get_connection, init_db
from kiosk.labels import SW, error_text
from kiosk.services import KioskError

NAIROBI_HOURS = 3


def create_app(db_path=None, testing=False):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DB_PATH=db_path or os.environ.get("DB_PATH", "kiosk.db"),
        KIOSK_NAME=os.environ.get("KIOSK_NAME", "Duka Langu"),
        TESTING=testing,
    )

    setup = get_connection(app.config["DB_PATH"])
    init_db(setup)
    setup.close()

    def db():
        if "db" not in g:
            g.db = get_connection(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.context_processor
    def inject_globals():
        return {"t": SW, "kiosk_name": app.config["KIOSK_NAME"]}

    @app.template_filter("kes")
    def kes(value):
        return f"{value:,}"

    # ---------- pages ----------

    @app.get("/")
    def stock():
        q = request.args.get("q", "").strip()
        products = services.list_products(db())
        if q:
            try:
                products = services.search_products(db(), q)
            except KioskError as err:
                flash(error_text(err), "error")
        return render_template("stock.html", products=products, q=q)

    @app.route("/uza", methods=["GET", "POST"])
    def sell():
        if request.method == "POST":
            try:
                result = services.sell(db(), request.form.get("product", ""),
                                       request.form.get("quantity", ""))
                flash(SW["sold_ok"].format(
                    quantity=result["quantity"], product=result["product"],
                    total=f"{result['total']:,}"), "ok")
            except KioskError as err:
                flash(error_text(err), "error")
            return redirect(url_for("sell"))
        sellable = [p for p in services.list_products(db()) if p["quantity"] > 0]
        return render_template("sell.html", products=sellable)

    @app.route("/ongeza", methods=["GET", "POST"])
    def add():
        if request.method == "POST":
            price = request.form.get("price", "").strip() or None
            try:
                action, product = services.add_or_restock(
                    db(), request.form.get("name", ""),
                    request.form.get("quantity", ""), price)
                msg = SW["restocked_ok"] if action == "restocked" else SW["added_ok"]
                flash(msg.format(product=product["name"], quantity=product["quantity"]), "ok")
            except KioskError as err:
                flash(error_text(err), "error")
            return redirect(url_for("add"))
        return render_template("add.html", products=services.list_products(db()))

    @app.get("/ripoti")
    def report():
        period = request.args.get("period", "today")
        today = datetime.now(timezone(timedelta(hours=NAIROBI_HOURS))).date().isoformat()
        data = services.sales_report(
            db(), date_from=today if period == "today" else None, tz_hours=NAIROBI_HOURS)
        return render_template("report.html", r=data, period=period)

    return app
