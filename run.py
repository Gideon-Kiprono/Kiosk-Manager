"""Start the app locally:  python run.py"""
from kiosk.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
