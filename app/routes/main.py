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
    has_back_thumb = os.path.exists(os.path.join(THUMBS_DIR, f"{scan_number}_b.jpg"))
    return render_template(
        "card.html",
        card=card,
        is_admin=is_admin,
        all_categories=all_categories,
        has_back_thumb=has_back_thumb,
    )


@main_bp.route("/card/<scan_number>/rotate", methods=["POST"])
@login_required
def rotate_thumbnail(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    side = request.args.get("side", "front")
    if side == "back":
        thumb_path = os.path.join(THUMBS_DIR, f"{scan_number}_b.jpg")
        if not os.path.exists(thumb_path):
            return jsonify({"success": False, "error": "Back thumbnail not found"}), 404
        img = Image.open(thumb_path).convert("RGB")
        img.rotate(180).save(thumb_path, "JPEG", quality=60, optimize=True)
    else:
        thumb_path = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
        if not os.path.exists(thumb_path):
            return jsonify({"success": False, "error": "Thumbnail not found"}), 404
        img = Image.open(thumb_path).convert("RGB")
        img.rotate(180).save(thumb_path, "JPEG", quality=60, optimize=True)
        card.thumbnail_rotated = not card.thumbnail_rotated
    db.session.commit()
    return jsonify({"success": True})


@main_bp.route("/card/<scan_number>/swap-sides", methods=["POST"])
@login_required
def swap_sides(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()

    front_path = os.path.join(THUMBS_DIR, f"{scan_number}.jpg")
    back_path = os.path.join(THUMBS_DIR, f"{scan_number}_b.jpg")
    temp_path = os.path.join(THUMBS_DIR, f"{scan_number}_temp.jpg")

    if os.path.exists(front_path) and os.path.exists(back_path):
        os.rename(front_path, temp_path)
        os.rename(back_path, front_path)
        os.rename(temp_path, back_path)
    elif os.path.exists(front_path):
        os.rename(front_path, back_path)
    elif os.path.exists(back_path):
        os.rename(back_path, front_path)

    card.drive_file_id_front, card.drive_file_id_back = card.drive_file_id_back, card.drive_file_id_front
    db.session.commit()
    return jsonify({"success": True})


@main_bp.route("/card/<scan_number>/identify-manual", methods=["POST"])
@login_required
def identify_manual(scan_number):
    from flask import flash, current_app
    from app.services.identify import ocr_card, card_num_stripped, best_match
    from app.services.tcg import get_card, assign_card

    card = Card.query.filter_by(scan_number=scan_number).first_or_404()

    pokemon_name = request.form.get("pokemon_name", "").strip()
    set_name_input = request.form.get("set_name", "").strip()
    card_number = request.form.get("card_number", "").strip()

    # Build an OCR-like dict from user input for TCG scoring
    user_ocr = {
        "card_name": pokemon_name,
        "card_number": card_number,
        "set_code": "",
        "total_in_set": "",
        "hp": "",
    }

    # OCR-verify: run actual OCR and check card number match
    ocr_verified = False
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            real_ocr = ocr_card(scan_number)
            if real_ocr:
                ocr_num = card_num_stripped(real_ocr.get("card_number") or "")
                user_num = card_num_stripped(card_number)
                if ocr_num and user_num and ocr_num == user_num:
                    ocr_verified = True
                    # Enrich with OCR set data for better TCG matching
                    user_ocr["set_code"] = real_ocr.get("set_code") or ""
                    user_ocr["total_in_set"] = real_ocr.get("total_in_set") or ""
                    user_ocr["hp"] = real_ocr.get("hp") or ""
        except Exception as e:
            current_app.logger.warning("OCR verify failed for %s: %s", scan_number, e)

    # Find best TCG match using scoring
    tcg_match = None
    score = 0
    if pokemon_name or card_number:
        try:
            tcg_match, score = best_match(user_ocr)
        except Exception as e:
            current_app.logger.error("TCG search failed for %s: %s", scan_number, e)

    # Persist
    if ocr_verified and tcg_match and score >= 3:
        try:
            full = get_card(tcg_match["tcg_card_id"])
            assign_card(card, full)
        except Exception as e:
            current_app.logger.error("assign_card failed for %s: %s", scan_number, e)
            card.card_name = pokemon_name or card.card_name
            card.set_name = set_name_input or card.set_name
            card.set_number = card_number or card.set_number
        card.identified = True
        card.identification_status = "User Updated - Verified"
        db.session.commit()
        flash("Identity saved and verified by OCR.", "success")
    else:
        card.card_name = pokemon_name or card.card_name
        card.set_name = set_name_input or card.set_name
        card.set_number = card_number or card.set_number
        card.identified = True
        card.identification_status = "User Updated - Unverified"
        db.session.commit()
        if api_key and not ocr_verified:
            flash("Identity saved. OCR card number mismatch — double-check the details.", "warning")
        else:
            flash("Identity saved (unverified — no API key configured).", "warning")

    return redirect(url_for("main.card_detail", scan_number=scan_number))


@main_bp.route("/card/<scan_number>/find-matches", methods=["POST"])
@login_required
def find_matches(scan_number):
    from flask import current_app
    from app.services.identify import ocr_card, card_num_stripped, score_result_with_reasons, detect_reverse_holo
    from app.services.tcg import search_cards_q

    Card.query.filter_by(scan_number=scan_number).first_or_404()

    ocr = None
    try:
        ocr = ocr_card(scan_number)
    except Exception as e:
        current_app.logger.error("OCR failed for %s: %s", scan_number, e)

    if not ocr:
        return jsonify({"error": "OCR failed — no image or Drive access unavailable"}), 422

    rh_result = None
    try:
        rh_result = detect_reverse_holo(scan_number)
    except Exception as e:
        current_app.logger.warning("RH detection failed for %s: %s", scan_number, e)

    card_name = (ocr.get("card_name") or "").strip()
    card_number_raw = (ocr.get("card_number") or "").strip()
    set_code = (ocr.get("set_code") or "").strip()
    num_stripped = card_num_stripped(card_number_raw)

    seen = {}

    def _fetch(q):
        try:
            return search_cards_q(q)
        except Exception as e:
            current_app.logger.warning("TCG query failed (%s): %s", q, e)
            return []

    for r in _fetch(f"number:{num_stripped} set.ptcgoCode:{set_code}") if (num_stripped and set_code) else []:
        if r.get("tcg_card_id") and r["tcg_card_id"] not in seen:
            seen[r["tcg_card_id"]] = r

    for r in _fetch(f'name:"{card_name}" number:{num_stripped}') if (card_name and num_stripped) else []:
        if r.get("tcg_card_id") and r["tcg_card_id"] not in seen:
            seen[r["tcg_card_id"]] = r

    if card_name:
        results = _fetch(f'name:"{card_name}"')
        if num_stripped:
            results = [r for r in results if card_num_stripped(r.get("set_number") or "") == num_stripped] or results
        for r in results:
            if r.get("tcg_card_id") and r["tcg_card_id"] not in seen:
                seen[r["tcg_card_id"]] = r

    candidates = []
    for result in seen.values():
        s, reasons = score_result_with_reasons(result, ocr)
        candidates.append({
            "tcg_card_id": result.get("tcg_card_id"),
            "card_name": result.get("card_name"),
            "set_name": result.get("set_name"),
            "set_code": result.get("set_ptcgo_code"),
            "card_number": result.get("set_number"),
            "release_date": result.get("release_date"),
            "tcg_image_url": result.get("tcg_image_url"),
            "market_price": result.get("market_price"),
            "score": s,
            "match_reasons": reasons,
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)

    return jsonify({
        "ocr": {
            "card_name": card_name,
            "card_number": card_number_raw,
            "set_code": set_code,
            "confidence": ocr.get("confidence", "low"),
        },
        "reverse_holo": rh_result,
        "candidates": candidates[:10],
    })


@main_bp.route("/card/<scan_number>/confirm-match", methods=["POST"])
@login_required
def confirm_match(scan_number):
    from app.services.tcg import get_card, assign_card

    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    data = request.get_json(silent=True) or {}
    tcg_card_id = (data.get("tcg_card_id") or "").strip()

    if not tcg_card_id:
        return jsonify({"error": "Missing tcg_card_id"}), 400

    try:
        full = get_card(tcg_card_id)
        assign_card(card, full)
        card.identified = True
        card.identification_status = "Examiner Confirmed"
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"success": True})


@main_bp.route("/card/<scan_number>/set-reverse-holo", methods=["POST"])
@login_required
def set_reverse_holo(scan_number):
    card = Card.query.filter_by(scan_number=scan_number).first_or_404()
    data = request.get_json(silent=True) or {}
    is_rh = data.get("is_reverse_holo")
    if is_rh is None:
        return jsonify({"error": "Missing is_reverse_holo"}), 400
    card.is_reverse_holo = bool(is_rh)
    card.reverse_holo_confirmed = True
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
