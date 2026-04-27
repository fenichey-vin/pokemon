from datetime import timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(days=7)

    db.init_app(app)

    from app.routes.main import main_bp
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        import os
        from sqlalchemy import inspect, text
        os.makedirs("/home/pokemon/data", exist_ok=True)
        db.create_all()

        # Add thumbnail_rotated column if upgrading from earlier schema
        insp = inspect(db.engine)
        if "cards" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("cards")]
            if "thumbnail_rotated" not in cols:
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE cards ADD COLUMN thumbnail_rotated BOOLEAN NOT NULL DEFAULT 0"
                    ))
                    conn.commit()

        # Seed AllowedEmail from ALLOWED_EMAILS config if table is empty (one-time migration)
        from app.models import AllowedEmail
        if AllowedEmail.query.count() == 0:
            for addr in app.config.get("ALLOWED_EMAILS", []):
                addr = addr.strip().lower()
                if addr:
                    db.session.add(AllowedEmail(email=addr, added_by="config"))
            db.session.commit()

    @app.cli.command("sync")
    def sync_command():
        """Sync Google Drive files into the catalog."""
        from app.services.drive import sync_drive
        with app.app_context():
            result = sync_drive()
            print(result)

    @app.cli.command("download-thumbs")
    def download_thumbs_command():
        """Download thumbnails for all cards that don't have a local thumb file."""
        import os
        from app.models import Card
        from app.services.drive import download_thumbnail, THUMBS_DIR
        with app.app_context():
            cards = Card.query.filter(Card.drive_file_id_front.isnot(None)).all()
            missing = [c for c in cards if not os.path.exists(os.path.join(THUMBS_DIR, f"{c.scan_number}.jpg"))]
            print(f"{len(missing)} thumbnail(s) to download.")
            ok = 0
            for card in missing:
                try:
                    download_thumbnail(card.drive_file_id_front, card.scan_number)
                    print(f"  #{card.scan_number} OK")
                    ok += 1
                except Exception as e:
                    print(f"  #{card.scan_number} FAILED: {e}")
            print(f"Done: {ok}/{len(missing)} downloaded.")

    @app.cli.command("identify-cards")
    def identify_cards_command():
        """Run AI vision identification on all unidentified cards."""
        from app.models import Card
        from app.services.identify import identify_card
        with app.app_context():
            cards = Card.query.filter_by(identified=False).all()
            print(f"{len(cards)} card(s) to identify.")
            ok = matched = 0
            for card in cards:
                try:
                    result = identify_card(card.scan_number)
                    status = "MATCHED" if result.get("matched") else "NO MATCH"
                    print(f"  #{card.scan_number} {status}: {result.get('pokemon_name', '?')} ({result.get('confidence', '?')})")
                    ok += 1
                    if result.get("matched"):
                        matched += 1
                except Exception as e:
                    print(f"  #{card.scan_number} FAILED: {e}")
            print(f"Done: {ok}/{len(cards)} processed, {matched} matched.")

    @app.cli.command("fetch-prices")
    def fetch_prices_command():
        """Fetch market prices for all identified cards via PriceCharting / TCG API."""
        from app.models import Card
        from app.services.pricing import fetch_price
        with app.app_context():
            cards = Card.query.filter_by(identified=True).all()
            print(f"{len(cards)} identified card(s).")
            ok = updated = 0
            for card in cards:
                try:
                    price = fetch_price(card)
                    if price is not None:
                        print(f"  #{card.scan_number} ${price:.2f}")
                        updated += 1
                    else:
                        print(f"  #{card.scan_number} no price found")
                    ok += 1
                except Exception as e:
                    print(f"  #{card.scan_number} FAILED: {e}")
            print(f"Done: {ok}/{len(cards)} processed, {updated} updated.")

    return app
