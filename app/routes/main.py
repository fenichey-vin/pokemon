import os
from functools import wraps
from PIL import Image
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from app import db
from app.models import Card, Category
from app.services.drive import THUMBS_DIR

main_bp = Blueprint("main", __name__)

PSA_GRADES = [
    "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5",
    "5", "5.5", "6", "6.5", "7", "7.5", "8", "8.5",
    "9", "9.5", "10",
]
PER_PAGE = 24


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@main_bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    grade = request.args.get("grade", "").strip()
    category_id = request.args.get("category", type=int)
    page = request.args.get("page", 1, type=int)

    cards_q = Card.search(query=q or None, grade=grade or None, category_id=category_id)
    pagination = cards_q.paginate(page=page, per_page=PER_PAGE, error_out=False)
    categories = Category.query.order_by(Category.name).all()

    return render_template(
        "index.html",
        cards=pagination.items,
        pagination=pagination,
        q=q,
        grade=grade,
        category_id=category_id,
        categories=categories,
        psa_grades=PSA_GRADES,
        total=pagination.total,
    )


@main_bp.route("/card/<scan_number>")
@login_required
def card_detail(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    is_admin = session.get("is_admin", False)
    all_categories = Category.query.order_by(Category.name).all()
    return render_template("card.html", card=card, is_admin=is_admin, all_categories=all_categories)


@main_bp.route("/card/<scan_number>/rotate", methods=["POST"])
@login_required
def rotate_thumbnail(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    thumb_path = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
    if not os.path.exists(thumb_path):
        return jsonify({"success": False, "error": "Thumbnail not found"}), 404
    img = Image.open(thumb_path).convert("RGB")
    img.rotate(180).save(thumb_path, "JPEG", quality=60, optimize=True)
    card.thumbnail_rotated = not card.thumbnail_rotated
    db.session.commit()
    return jsonify({"success": True})


@main_bp.route("/card/<scan_number>/categories", methods=["POST"])
@login_required
def add_category(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    data = request.get_json(silent=True) or {}
    cat_id = data.get("category_id") or request.form.get("category_id", type=int)
    if not cat_id:
        return jsonify({"error": "Missing category_id"}), 400
    cat = db.session.get(Category, cat_id)
    if cat is None:
        return jsonify({"error": "Category not found"}), 404
    if cat not in card.categories:
        card.categories.append(cat)
        db.session.commit()
    return jsonify({"success": True, "category": cat.to_dict()})


@main_bp.route("/card/<scan_number>/categories/<int:cat_id>", methods=["DELETE"])
@login_required
def remove_category(scan_number, cat_id):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    cat = db.session.get(Category, cat_id)
    if cat and cat in card.categories:
        card.categories.remove(cat)
        db.session.commit()
    return jsonify({"success": True})
