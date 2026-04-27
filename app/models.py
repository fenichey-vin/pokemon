from datetime import datetime, timezone
from sqlalchemy import or_
from app import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LoginCode(db.Model):
    __tablename__ = "login_codes"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)


class AllowedEmail(db.Model):
    __tablename__ = "allowed_emails"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    added_at = db.Column(db.DateTime, default=_utcnow)
    added_by = db.Column(db.String(255), nullable=True)


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    attempted_at = db.Column(db.DateTime, default=_utcnow)


card_categories = db.Table(
    "card_categories",
    db.Column("card_id", db.Integer, db.ForeignKey("cards.id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("categories.id"), primary_key=True),
)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Card(db.Model):
    __tablename__ = "cards"

    id = db.Column(db.Integer, primary_key=True)
    scan_number = db.Column(db.String(10), unique=True, nullable=False)
    drive_file_id_front = db.Column(db.String(200))
    drive_file_id_back = db.Column(db.String(200), nullable=True)
    thumbnail_url = db.Column(db.String(500))
    thumbnail_rotated = db.Column(db.Boolean, default=False, nullable=False)
    date_scanned = db.Column(db.DateTime, nullable=True)

    tcg_card_id = db.Column(db.String(100), nullable=True)
    card_name = db.Column(db.String(200), nullable=True)
    set_name = db.Column(db.String(200), nullable=True)
    set_number = db.Column(db.String(50), nullable=True)
    release_date = db.Column(db.String(50), nullable=True)
    tcg_image_url = db.Column(db.String(500), nullable=True)

    grade = db.Column(db.String(10), nullable=True)
    grade_notes = db.Column(db.Text, nullable=True)

    market_price = db.Column(db.Float, nullable=True)
    price_fetched_at = db.Column(db.DateTime, nullable=True)

    identified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    categories = db.relationship("Category", secondary=card_categories, backref="cards")

    @property
    def grade_color(self):
        if not self.grade:
            return "grey"
        try:
            g = float(self.grade)
        except ValueError:
            return "grey"
        if g >= 7.5:
            return "green"
        if g >= 5:
            return "yellow"
        return "red"

    @property
    def thumbnail(self):
        if self.drive_file_id_front:
            return f"/static/thumbs/{self.scan_number}.jpg"
        return None

    @property
    def front_link(self):
        if self.drive_file_id_front:
            return f"https://drive.google.com/file/d/{self.drive_file_id_front}/view"
        return None

    @property
    def back_link(self):
        if self.drive_file_id_back:
            return f"https://drive.google.com/file/d/{self.drive_file_id_back}/view"
        return None

    @property
    def back_thumbnail(self):
        if self.drive_file_id_back:
            return f"/static/thumbs/{self.scan_number}_b.jpg"
        return None

    @classmethod
    def search(cls, query=None, grade=None, category_id=None):
        q = cls.query
        if query:
            like = f"%{query}%"
            q = q.filter(
                or_(
                    cls.card_name.ilike(like),
                    cls.set_name.ilike(like),
                    cls.scan_number.ilike(like),
                )
            )
        if grade == "ungraded":
            q = q.filter(cls.grade.is_(None))
        elif grade:
            q = q.filter(cls.grade == grade)
        if category_id:
            q = q.filter(cls.categories.any(Category.id == category_id))
        return q.order_by(cls.scan_number)

    def to_dict(self):
        return {
            "id": self.id,
            "scan_number": self.scan_number,
            "card_name": self.card_name,
            "set_name": self.set_name,
            "set_number": self.set_number,
            "release_date": self.release_date,
            "grade": self.grade,
            "grade_color": self.grade_color,
            "market_price": self.market_price,
            "identified": self.identified,
            "thumbnail_url": self.thumbnail,
            "front_link": self.front_link,
            "back_link": self.back_link,
        }
