"""V139 MCP tool registry routes.

Expose the AI Worker's read-only REST APIs as MCP-style tool definitions for
external AI assistants.  Zero new dependencies — this is a rest2mcp-style
bridge: the manifest describes tools, and each tool is invoked through the
existing authenticated REST endpoints.
"""
from flask import jsonify, request

from app.routes.scoring import scoring_bp
from core.mcp_tools import manifest


@scoring_bp.get("/api/mcp/manifest")
def mcp_manifest():
    """MCP tool registry: list all available read-only tools."""
    return jsonify(manifest())


@scoring_bp.get("/api/mcp/health")
def mcp_health():
    """MCP bridge health: confirm the tool registry is available."""
    return jsonify({"version": "mcp-bridge-v1", "status": "ok",
                    "tools": len(manifest()["tools"]),
                    "read_only": True,
                    "production_actions_enabled": False})


@scoring_bp.get("/api/mcp/tools/<tool_name>")
def mcp_tool_detail(tool_name):
    """Describe a single tool: definition + invocation example."""
    m = manifest()
    for t in m["tools"]:
        if t["name"] == tool_name:
            return jsonify({**t, "version": m["version"],
                            "read_only": True,
                            "note": "调用时需携带控制台同款 Basic Auth 凭据；仅返回数据，不修改 Miniflux。"})
    return jsonify({"error": "tool_not_found", "available": [t["name"] for t in m["tools"]]}), 404
