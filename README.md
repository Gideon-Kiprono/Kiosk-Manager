# Kiosk Manager

Stock and sales management for a small kiosk. Started as a command-line capstone project (see `legacy/`), now growing into a Flask web app.

## Status

- [x] Stage 1: project structure, business logic as reusable functions, SQLite database, tests
- [x] Stage 2: Flask web app in Swahili (stock, sell, add/restock, report, search)
- [x] Stage 3: accounts (sign-up, login, demo), each kiosk sees only its own data
- [ ] Stage 4: dashboard, charts, polish
- [ ] Stage 5: deployment

## Run the tests

    python -m unittest -v

## Layout

    kiosk/        business logic (db.py, services.py), no input() or print()
    tests/        unit tests
    legacy/       the original command-line version, kept for reference

## Run the website locally

    pip install -r requirements.txt
    python import_legacy.py      # optional: load the original stock
    python run.py                # open http://127.0.0.1:5000

Open the site, then **Jisajili** (sign up) or **Jaribu demo** (try a demo kiosk with sample data).
If you ran `import_legacy.py` first, the first account you create takes over that stock.

Settings (environment variables):

| Variable | Meaning |
|---|---|
| `DB_PATH` | Database file (default `kiosk.db`) |
| `SECRET_KEY` | Signs login cookies. Set a long random value in production |
| `COOKIE_SECURE` | Set to `1` when the site is served over HTTPS |

## Security notes

- Passwords are stored as salted hashes, never as text.
- Every form carries a CSRF token; login is limited to 5 failed attempts per email per 15 minutes.
- Every database query is filtered by the logged-in owner, and tests check that one kiosk cannot read or change another's data.
- Demo accounts are deleted after 24 hours.
