# Pokemon Card Catalog

A Flask web application for cataloging Pokemon cards, backed by Google Drive scans and the Pokemon TCG API.

## Requirements

- Python 3.10+
- A Google Cloud project with:
  - OAuth2 credentials (Web application type)
  - A service account with Google Drive API access
- A Pokemon TCG API key (optional but recommended)
- nginx + systemd on Ubuntu

---

## Setup

### 1. Clone and create virtualenv

```bash
cd /home/pokemon
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy the example and fill in all values:

```bash
cp .env.example .env
nano .env
```

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth2 client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth2 client secret |
| `ALLOWED_EMAILS` | Comma-separated list of Google emails allowed to log in |
| `POKEMON_TCG_API_KEY` | From https://dev.pokemontcg.io — free tier is fine |
| `ADMIN_PASSWORD` | Password for the admin dashboard (separate from Google login) |
| `SECRET_KEY` | Long random string for Flask session signing (`python3 -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | Leave as default: `sqlite:////home/pokemon/data/catalog.db` |
| `GOOGLE_DRIVE_FOLDER_ID` | Already set to your Drive folder |
| `SERVICE_ACCOUNT_JSON` | Path to service account JSON — already set |

### 3. Get a Pokemon TCG API key

1. Go to https://dev.pokemontcg.io
2. Register for a free account
3. Copy your API key into `.env` as `POKEMON_TCG_API_KEY`

Without the key the app works but is rate-limited to 1,000 requests/day.

### 4. Set up Google OAuth2

1. Go to Google Cloud Console → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Add `http://fordlover.duckdns.org:5005/auth/callback` as an authorized redirect URI
4. Copy the Client ID and Secret into `.env`

### 5. Initialize the database

```bash
source venv/bin/activate
flask --app run db   # tables created automatically on first start
python run.py        # or use gunicorn below
```

The `data/` directory and SQLite database are created automatically.

### 6. Enable the nginx config

```bash
# Copy or symlink
ln -s /home/pokemon/pokemon.nginx.conf /etc/nginx/sites-enabled/pokemon

# Test and reload
nginx -t && systemctl reload nginx
```

### 7. Install and start the systemd service

```bash
cp /home/pokemon/pokemon.service /etc/systemd/system/pokemon.service
systemctl daemon-reload
systemctl enable pokemon
systemctl start pokemon
systemctl status pokemon
```

View logs:
```bash
journalctl -u pokemon -f
```

### 8. Run Drive sync manually

```bash
cd /home/pokemon
source venv/bin/activate
flask --app run sync
```

Or click **Sync Drive** in the Admin dashboard.

---

## Usage

### Catalog

Navigate to `http://fordlover.duckdns.org` and sign in with a Google account in `ALLOWED_EMAILS`.

### Admin

1. Click **Admin Login** in the header
2. Enter the `ADMIN_PASSWORD`
3. Use **Sync Drive** to import new scans from Google Drive
4. Use **Identify** on any pending card to search the TCG API and assign an identity
5. Use **Refresh Prices** to update market prices for all identified cards

### Drive file naming

The sync expects files named:
- `Pokemon_0001.jpg` — front of card
- `Pokemon_0001_b.jpg` — back of card (optional)

Four-digit zero-padded scan number. Both `.jpg` and `.png` extensions are supported.

### Grading

Grades use the PSA scale (1–10 in 0.5 increments). Color coding:
- **Green**: 7.5 and above
- **Yellow**: 5.0 to 7.0
- **Red**: below 5.0
- **Grey**: ungraded

---

## Project Structure

```
/home/pokemon/
  app/
    __init__.py          # App factory, OAuth setup
    models.py            # Card SQLAlchemy model
    routes/
      main.py            # Catalog and card detail routes
      admin.py           # Admin dashboard, edit, delete, identify
      auth.py            # Google OAuth2 login/callback/logout
      api.py             # JSON API for TCG search (used by admin JS)
    services/
      drive.py           # Google Drive sync via service account
      tcg.py             # Pokemon TCG API client
    templates/           # Jinja2 HTML templates
    static/              # CSS and vanilla JS
  data/                  # SQLite database (gitignored)
  config.py              # Config loaded from .env
  run.py                 # WSGI entry point
  requirements.txt
  pokemon.nginx.conf     # nginx reverse proxy config
  pokemon.service        # systemd unit file
  .env.example           # Template for .env
```
