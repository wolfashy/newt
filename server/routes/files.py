import subprocess, tempfile
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file
bp = Blueprint("files", __name__)

@bp.route("/screenshot", methods=["GET"])
def screenshot():
    path = Path(tempfile.gettempdir()) / "newt-screenshot.png"
    try:
        subprocess.run(["screencapture", "-x", str(path)], capture_output=True, timeout=5)
        if path.exists(): return send_file(str(path), mimetype="image/png")
    except Exception: pass
    return jsonify({"ok": False, "error": "Failed"}), 500

@bp.route("/file", methods=["GET"])
def get_file():
    path = request.args.get("path", "").strip()
    if not path: return jsonify({"ok": False, "error": "No path"}), 400
    p = Path(path).expanduser()
    if not p.exists(): return jsonify({"ok": False, "error": "Not found"}), 404
    if p.is_dir():
        return jsonify({"ok": True, "type": "directory", "items": [f.name for f in sorted(p.iterdir())[:50]]})
    return send_file(str(p))
