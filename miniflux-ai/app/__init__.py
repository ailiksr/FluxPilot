"""Flask application for miniflux-AI."""

import base64
import hashlib
import hmac
import os

from flask import Flask, jsonify, request, Response


_PUBLIC_PATHS = {"/healthz", "/api/miniflux-ai", "/rss/digest", "/rss/curated"}


def _basic_credentials_valid() -> bool:
    expected_user = os.environ.get("RSS_AI_ADMIN_USER", "").strip()
    expected_password = os.environ.get("RSS_AI_ADMIN_PASSWORD", "")
    if not expected_user or not expected_password:
        return False
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        user, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        return False
    return hmac.compare_digest(user, expected_user) and hmac.compare_digest(password, expected_password)


def _auth_required() -> Response:
    return Response(
        "Authentication required\n",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="RSS AI Worker", charset="UTF-8"'},
        mimetype="text/plain",
    )


def create_app() -> Flask:
    """Create the Flask application and register the API blueprints."""
    app = Flask(__name__)

    @app.before_request
    def protect_management_surface():
        # Health, Miniflux's HMAC-protected webhook, the digest feed, and static
        # assets remain public. Everything else (UI and API) requires auth.
        if request.path in _PUBLIC_PATHS or request.path.startswith("/static/"):
            return None
        if not _basic_credentials_valid():
            return _auth_required()
        return None

    @app.get("/healthz")
    def healthz():
        """Lightweight liveness probe; does not call Miniflux or the LLM."""
        return jsonify({"status": "ok", "service": "miniflux-ai"})

    @app.get("/api/system-status")
    def system_status():
        """Compact read-only status for the AI Worker operations console."""
        from core.storage import status as storage_status
        from core.control_store import status as write_status
        from core.feed_health import report as feed_health_report
        health = feed_health_report()
        return jsonify({
            "version": "system-status-v1",
            "service": "miniflux-ai",
            "storage": storage_status(),
            "writes": write_status(),
            "feed_health": {
                "feeds": len(health),
                "healthy": sum(1 for item in health if item.get("action") == "healthy"),
                "observe": sum(1 for item in health if item.get("action") == "observe"),
                "investigate": sum(1 for item in health if item.get("action") == "investigate"),
            },
        })

    @app.get("/api/storage-mode")
    def storage_mode():
        from core.storage import status
        from core.control_store import status as write_status
        return jsonify({"version": "storage-adapter-v1", **status(), **write_status()})

    @app.get("/api/storage-consistency")
    def storage_consistency():
        """Read-only JSONL/PostgreSQL control-plane consistency report."""
        import json
        from pathlib import Path
        report = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data")) / "control_consistency.json"
        if not report.exists():
            return jsonify({"status": "unknown", "reason": "consistency_check_not_run"}), 503
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return jsonify({"status": "error", "reason": "consistency_report_unreadable"}), 503
        return jsonify({"status": "ok" if data.get("ok") else "mismatch", **data}), (200 if data.get("ok") else 503)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    from app.routes.digest import digest_bp
    from app.routes.curated import curated_bp
    from app.routes.webhook import webhook_bp
    from app.routes.scoring import scoring_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(scoring_bp)
    app.register_blueprint(digest_bp)
    app.register_blueprint(curated_bp)

    return app
