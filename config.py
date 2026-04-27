import os
from dotenv import load_dotenv

load_dotenv('/home/pokemon/.env', override=True)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:////home/pokemon/data/catalog.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ALLOWED_EMAILS = [
        e.strip()
        for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
        if e.strip()
    ]

    POKEMON_TCG_API_KEY = os.environ.get("POKEMON_TCG_API_KEY")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    GOOGLE_DRIVE_FOLDER_ID = os.environ.get(
        "GOOGLE_DRIVE_FOLDER_ID", "1SlUKKpjYKt_sxbhTpP8x42tD4nWTITXM"
    )
    SERVICE_ACCOUNT_JSON = os.environ.get(
        "SERVICE_ACCOUNT_JSON", "/home/pokemon/service_account.json"
    )

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    MAIL_SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "")
    MAIL_SMTP_PORT = os.environ.get("MAIL_SMTP_PORT", "587")
    MAIL_SMTP_USER = os.environ.get("MAIL_SMTP_USER", "")
    MAIL_SMTP_PASSWORD = os.environ.get("MAIL_SMTP_PASSWORD", "")
