import threading
from functools import wraps
from flask import (
    Blueprint, render_template, redirect, url_for,
    request, session, flash, current_app, jsonify
)
from app import db
from app.models import Card

admin_bp = Blueprint("admin", __name__)

_task_lock = threading.Lock()
_tasks = {"identify": None, "prices": None}

PSA_GRADES = [
    "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5",
    "5", "5.5", "6", "6.5", "7", "7.5", "8", "8.5",
    "9", "9.5", "10",
]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("auth.login"))
        if not session.get("is_admin"):
            return redirect(url_for("admin.admin_login"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("", methods=["GET", "POST"])
@login_required
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin.admin_login"))

    from app.models import Category
    tab = request.args.get("tab", "all")
    q = request.args.get("q", "").strip()
    grade = request.args.get("grade", "").strip()
    category_id = request.args.get("category", type=int)

    cards_q = Card.search(query=q or None, grade=grade or None, category_id=category_id)
    if tab == "pending":
        cards_q = cards_q.filter(Card.identified == False)
    cards = cards_q.all()
    categories = Category.query.order_by(Category.name).all()

    return render_template(
        "admin.html", cards=cards, tab=tab, psa_grades=PSA_GRADES,
        q=q, grade=grade, category_id=category_id, categories=categories,
    )


@admin_bp.route("/login", methods=["GET", "POST"])
@login_required
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin.admin_dashboard"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == current_app.config["ADMIN_PASSWORD"]:
            session["is_admin"] = True
            return redirect(url_for("admin.admin_dashboard"))
        error = "Invalid password."

    return render_template("admin_login.html", error=error)


@admin_bp.route("/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("main.index"))


@admin_bp.route("/sync", methods=["POST"])
@admin_required
def sync():
    from app.services.drive import sync_drive
    try:
        msg = sync_drive()
        flash(msg, "success")
    except Exception as e:
        flash(f"Sync failed: {e}", "error")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/refresh-prices", methods=["POST"])
@admin_required
def refresh_prices():
    from app.services.tcg import refresh_all_prices
    try:
        msg = refresh_all_prices()
        flash(msg, "success")
    except Exception as e:
        flash(f"Price refresh failed: {e}", "error")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/card/<scan_number>/edit", methods=["GET", "POST"])
@admin_required
def edit_card(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()

    if request.method == "POST":
        card.card_name = request.form.get("card_name") or None
        card.set_name = request.form.get("set_name") or None
        card.set_number = request.form.get("set_number") or None
        card.release_date = request.form.get("release_date") or None
        card.tcg_card_id = request.form.get("tcg_card_id") or None
        card.tcg_image_url = request.form.get("tcg_image_url") or None
        card.grade = request.form.get("grade") or None
        card.grade_notes = request.form.get("grade_notes") or None

        price_str = request.form.get("market_price", "").strip()
        card.market_price = float(price_str) if price_str else None

        card.identified = bool(card.card_name)

        from datetime import datetime, timezone
        card.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        flash(f"Card #{scan_number} updated.", "success")
        return redirect(url_for("admin.admin_dashboard"))

    return render_template("edit_card.html", card=card, psa_grades=PSA_GRADES)


@admin_bp.route("/card/<scan_number>/delete", methods=["POST"])
@admin_required
def delete_card(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    db.session.delete(card)
    db.session.commit()
    flash(f"Card #{scan_number} deleted.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/card/<scan_number>/identify", methods=["POST"])
@admin_required
def identify_card(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    tcg_card_id = request.form.get("tcg_card_id")
    if not tcg_card_id:
        flash("No TCG card ID provided.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    from app.services.tcg import get_card, assign_card
    try:
        data = get_card(tcg_card_id)
        assign_card(card, data)
        db.session.commit()
        flash(f"Card #{scan_number} identified as {card.card_name}.", "success")
    except Exception as e:
        flash(f"Identification failed: {e}", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/pending")
@admin_required
def pending():
    from app.models import Category
    cards = Card.query.filter_by(identified=False).order_by(Card.scan_number).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template("admin.html", cards=cards, tab="pending", psa_grades=PSA_GRADES,
                           q="", grade="", category_id=None, categories=categories)


@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    from app.models import Category
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name required.", "error")
        elif Category.query.filter_by(name=name).first():
            flash(f"Category '{name}' already exists.", "error")
        else:
            db.session.add(Category(name=name))
            db.session.commit()
            flash(f"Category '{name}' created.", "success")
    cats = Category.query.order_by(Category.name).all()
    return render_template("categories.html", categories=cats)


@admin_bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@admin_required
def delete_category(cat_id):
    from app.models import Category
    cat = db.session.get(Category, cat_id)
    if cat is None:
        flash("Category not found.", "error")
    elif cat.cards:
        flash(f"Cannot delete '{cat.name}': {len(cat.cards)} card(s) still use it.", "error")
    else:
        db.session.delete(cat)
        db.session.commit()
        flash(f"Category '{cat.name}' deleted.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/identify-cards", methods=["POST"])
@admin_required
def identify_cards_bulk():
    with _task_lock:
        if _tasks["identify"] and _tasks["identify"]["status"] == "running":
            return jsonify({"status": "already_running"}), 409
        _tasks["identify"] = {"status": "running", "done": 0, "total": 0, "errors": 0}

    app = current_app._get_current_object()

    def run():
        with app.app_context():
            from app.services.identify import identify_card
            cards = Card.query.filter_by(identified=False).all()
            with _task_lock:
                _tasks["identify"]["total"] = len(cards)
            done = errors = 0
            for card in cards:
                try:
                    identify_card(card.scan_number)
                except Exception:
                    errors += 1
                done += 1
                with _task_lock:
                    _tasks["identify"]["done"] = done
                    _tasks["identify"]["errors"] = errors
            with _task_lock:
                _tasks["identify"]["status"] = "done"

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"}), 202


@admin_bp.route("/fetch-prices", methods=["POST"])
@admin_required
def fetch_prices_bulk():
    with _task_lock:
        if _tasks["prices"] and _tasks["prices"]["status"] == "running":
            return jsonify({"status": "already_running"}), 409
        _tasks["prices"] = {"status": "running", "done": 0, "total": 0, "errors": 0}

    app = current_app._get_current_object()

    def run():
        with app.app_context():
            from app.services.pricing import fetch_price
            cards = Card.query.filter_by(identified=True).all()
            with _task_lock:
                _tasks["prices"]["total"] = len(cards)
            done = errors = 0
            for card in cards:
                try:
                    fetch_price(card)
                except Exception:
                    errors += 1
                done += 1
                with _task_lock:
                    _tasks["prices"]["done"] = done
                    _tasks["prices"]["errors"] = errors
            with _task_lock:
                _tasks["prices"]["status"] = "done"

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"}), 202


@admin_bp.route("/task-status")
@admin_required
def task_status():
    with _task_lock:
        return jsonify({"identify": _tasks["identify"], "prices": _tasks["prices"]})


@admin_bp.route("/access")
@admin_required
def access_control():
    from app.models import AllowedEmail
    emails = AllowedEmail.query.order_by(AllowedEmail.added_at).all()
    return render_template("admin_access.html", allowed_emails=emails)


@admin_bp.route("/access/add", methods=["POST"])
@admin_required
def access_add():
    from app.models import AllowedEmail
    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("Email address required.", "error")
    elif AllowedEmail.query.filter_by(email=email).first():
        flash(f"{email} is already in the allowlist.", "error")
    else:
        db.session.add(AllowedEmail(email=email, added_by=session["user_email"]))
        db.session.commit()
        flash(f"{email} added to allowlist.", "success")
    return redirect(url_for("admin.access_control"))


@admin_bp.route("/access/remove/<int:ae_id>", methods=["POST"])
@admin_required
def access_remove(ae_id):
    from app.models import AllowedEmail
    ae = db.session.get(AllowedEmail, ae_id)
    if ae is None:
        flash("Entry not found.", "error")
    elif ae.email == session.get("user_email", "").lower():
        flash("You cannot remove your own email.", "error")
    else:
        db.session.delete(ae)
        db.session.commit()
        flash(f"{ae.email} removed from allowlist.", "success")
    return redirect(url_for("admin.access_control"))
