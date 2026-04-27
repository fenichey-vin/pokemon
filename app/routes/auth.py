import random
import string
from datetime import datetime, timezone, timedelta
from flask import (
    Blueprint, redirect, url_for, session,
    render_template, current_app, request,
)
from app import db
from app.models import LoginCode, AllowedEmail, LoginAttempt

auth_bp = Blueprint("auth", __name__)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_email" in session:
        return redirect(url_for("main.index"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            error = "Please enter your email address."
        else:
            # Check allowlist (empty table = no restriction)
            total = AllowedEmail.query.count()
            if total > 0 and not AllowedEmail.query.filter_by(email=email).first():
                error = "Access denied. This email is not authorized."
            else:
                now = _utcnow()

                # Rate limit: 10+ login requests for this email in the last hour
                hour_cutoff = now - timedelta(hours=1)
                recent_requests = LoginCode.query.filter(
                    LoginCode.email == email,
                    LoginCode.created_at >= hour_cutoff,
                ).count()
                if recent_requests >= 10:
                    error = "Too many requests. Try again later."
                else:
                    # Parallel-worker dedup: redirect if a fresh code already exists
                    recent_cutoff = now - timedelta(seconds=10)
                    recent = LoginCode.query.filter(
                        LoginCode.email == email,
                        LoginCode.used == False,
                        LoginCode.expires_at > now,
                        LoginCode.created_at >= recent_cutoff,
                    ).first()
                    if recent:
                        return redirect(url_for("auth.verify", email=email))

                    code = "".join(random.choices(string.digits, k=6))

                    # Invalidate any outstanding unused codes for this email
                    LoginCode.query.filter_by(email=email, used=False).update({"used": True})

                    lc = LoginCode(
                        email=email,
                        code=code,
                        created_at=now,
                        expires_at=now + timedelta(minutes=15),
                        used=False,
                    )
                    db.session.add(lc)
                    db.session.commit()

                    from app.services.mail import send_login_code
                    if not send_login_code(email, code):
                        db.session.delete(lc)
                        db.session.commit()
                        error = "Email could not be sent, please contact the administrator."
                    else:
                        return redirect(url_for("auth.verify", email=email))

    return render_template("login.html", error=error)


@auth_bp.route("/verify", methods=["GET", "POST"])
def verify():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        submitted = request.form.get("code", "").strip()
        now = _utcnow()

        # Rate limit: 5+ failed attempts for this email in the last 15 minutes
        attempt_cutoff = now - timedelta(minutes=15)
        recent_fails = LoginAttempt.query.filter(
            LoginAttempt.email == email,
            LoginAttempt.attempted_at >= attempt_cutoff,
        ).count()
        if recent_fails >= 5:
            error = "Too many attempts. Please request a new code."
        else:
            lc = LoginCode.query.filter_by(email=email, code=submitted, used=False).first()

            if lc is None:
                db.session.add(LoginAttempt(email=email, attempted_at=now))
                db.session.commit()
                error = "Invalid code. Please check and try again."
            elif lc.expires_at < now:
                lc.used = True
                db.session.add(LoginAttempt(email=email, attempted_at=now))
                db.session.commit()
                error = "Code expired. Please request a new one."
            else:
                lc.used = True
                LoginAttempt.query.filter_by(email=email).delete()
                db.session.commit()
                session.permanent = True
                session["user_email"] = email
                session["user_name"] = email
                return redirect(url_for("main.index"))

    return render_template("verify.html", email=email, error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
