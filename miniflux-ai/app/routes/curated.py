"""Curated high-value article RSS feed routes."""
from flask import Blueprint, Response, request

from common.logger import get_logger
from core.curated_feed import generate_curated_rss

logger = get_logger(__name__)
curated_bp = Blueprint("curated", __name__)


@curated_bp.route("/rss/curated", methods=["GET"])
def rss_curated() -> Response:
    """RSS feed of AI-scored high-value articles.

    Query params:
        min_score: minimum AI score (default 70).
        limit: max entries (default 30, max 100).
    """
    try:
        min_score = request.args.get("min_score", "70")
        try:
            min_score = max(0, min(100, int(min_score)))
        except (TypeError, ValueError):
            min_score = 70
        limit = request.args.get("limit", "30")
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 30
        rss = generate_curated_rss(min_score=min_score, limit=limit)
        return Response(rss, mimetype="application/rss+xml")
    except Exception as e:
        logger.error(f"Failed to generate curated RSS feed: {e}")
        return Response("curated feed unavailable", status=500, mimetype="text/plain")
