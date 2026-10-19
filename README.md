# Kiosk Manager

Stock and sales management for a small kiosk. Started as a command-line capstone project (see `legacy/`), now growing into a Flask web app.

## Status

- [x] Stage 1: project structure, business logic as reusable functions, SQLite database, tests
- [ ] Stage 2: Flask web app (stock, sell, report, search)
- [ ] Stage 3: login and per-kiosk data
- [ ] Stage 4: dashboard, charts, polish
- [ ] Stage 5: deployment

## Run the tests

    python -m unittest -v

## Layout

    kiosk/        business logic (db.py, services.py), no input() or print()
    tests/        unit tests
    legacy/       the original command-line version, kept for reference
