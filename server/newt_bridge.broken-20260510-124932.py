"""Newt Bridge — Flask HTTP entry point."""
import logging
from flask import Flask
from core.config import NEWT_HOST, NEWT_PORT
from routes import register_blueprints

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
app = Flask(__name__)
register_blueprints(app)

if __name__ == "__main__":
    print(f"Newt v2 starting on {NEWT_HOST}:{NEWT_PORT} — 101 tools loaded")
    app.run(host=NEWT_HOST, port=NEWT_PORT, threaded=True)
