"""MCP tool registry for the RSS AI Worker.

Exposes the AI Worker's read-only REST APIs as MCP-style tool definitions so
external AI assistants (Claude Desktop, Cursor, etc.) can discover and call
them.  Zero new dependencies: tools are described here and invoked through
the existing authenticated REST endpoints.

Every tool is read-only; none of them mutate Miniflux or enable production
actions.  See the security boundaries in AI_HANDOVER.md.
"""

TOOLS = [
    {
        "name": "get_scores",
        "description": "列出已评分的文章（含 AI 评分、Judge 维度、triage 分流、自主决策）。用于查看当前所有已处理文章及其质量评估。",
        "method": "GET",
        "path": "/api/scores",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/scores",
    },
    {
        "name": "get_recommendations",
        "description": "获取 AI 推荐阅读列表（按推荐分数降序，含 Feed 权重调整）。",
        "method": "GET",
        "path": "/api/recommendations",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/recommendations",
    },
    {
        "name": "get_trends",
        "description": "获取趋势分析：主题热度变化（近7天动量）、热门关键词、内容类型分布、Feed 活跃度。",
        "method": "GET",
        "path": "/api/scoring/trends",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/scoring/trends",
    },
    {
        "name": "get_feed_health",
        "description": "获取各 Feed 抓取健康：成功率、平均/P95 延迟、连续失败次数、最新状态。",
        "method": "GET",
        "path": "/api/scoring/feed-health",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/scoring/feed-health",
    },
    {
        "name": "get_feed_health_trends",
        "description": "获取 Feed 抓取健康 24h 趋势：按小时分桶的成功率/延迟时间序列 + 最近错误事件。",
        "method": "GET",
        "path": "/api/scoring/feed-health/trends",
        "input_schema": {
            "type": "object",
            "properties": {"hours": {"type": "integer", "description": "时间窗口小时数，默认24，最大168"}},
            "additionalProperties": False,
        },
        "example": "GET /api/scoring/feed-health/trends?hours=24",
    },
    {
        "name": "get_feed_quality",
        "description": "获取 Feed 内容质量分析：平均分、低质率、营销率、AI 维护建议（保持/观察/降权）。",
        "method": "GET",
        "path": "/api/scoring/feed-quality-v2",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/scoring/feed-quality-v2",
    },
    {
        "name": "get_feed_policy",
        "description": "获取各 Feed 的 AI 推荐权重与策略（只读）。",
        "method": "GET",
        "path": "/api/feed-policy",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/feed-policy",
    },
    {
        "name": "get_autonomous_decisions",
        "description": "获取 AI 自主分流统计与最近决策（优先阅读/保留/跳过/边界复核）及其原因。",
        "method": "GET",
        "path": "/api/scoring/autonomous",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/scoring/autonomous",
    },
    {
        "name": "get_preference_profile",
        "description": "获取用户偏好画像：正向/回避主题、兴趣/回避关键词、内容类型偏好（来自人工审核决策）。",
        "method": "GET",
        "path": "/api/preferences/profile",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/preferences/profile",
    },
    {
        "name": "get_backtest",
        "description": "获取 Shadow 回测结果：AI 自动路由 vs 人工审核的一致性（覆盖率、精度、混淆矩阵）。",
        "method": "GET",
        "path": "/api/scoring/backtest",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/scoring/backtest",
    },
    {
        "name": "get_benchmark_pending",
        "description": "获取待人工审核的文章队列（边界/低置信候选）。",
        "method": "GET",
        "path": "/api/benchmark/pending",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/benchmark/pending",
    },
    {
        "name": "get_archive_review",
        "description": "获取归档复审候选列表（AI 建议归档、需人工确认的文章）。",
        "method": "GET",
        "path": "/api/console/archive-review",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/console/archive-review",
    },
    {
        "name": "get_article_detail",
        "description": "获取单篇文章详情：AI Judge 维度、taxonomy、人工审核状态。",
        "method": "GET",
        "path": "/api/benchmark/{entry_id}/detail",
        "input_schema": {
            "type": "object",
            "properties": {"entry_id": {"type": "integer", "description": "文章 entry_id"}},
            "required": ["entry_id"],
            "additionalProperties": False,
        },
        "example": "GET /api/benchmark/6/detail",
    },
    {
        "name": "get_system_status",
        "description": "获取系统运行状态：存储模式、写入状态、Outbox、Feed 健康摘要。",
        "method": "GET",
        "path": "/api/system-status",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/system-status",
    },
    {
        "name": "get_console_summary",
        "description": "获取控制台摘要：已评分文章数、AI 自动分流统计、归档复审数、生产动作状态。",
        "method": "GET",
        "path": "/api/console/summary",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/console/summary",
    },
    {
        "name": "search_articles",
        "description": "全文搜索文章（Miniflux 全文 + AI 评分数据混合），返回标题、链接、AI 评分、来源。支持中文关键词。",
        "method": "GET",
        "path": "/api/search",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回条数，默认20，最大50"},
            },
            "required": ["q"],
            "additionalProperties": False,
        },
        "example": "GET /api/search?q=AI&limit=10",
    },
    {
        "name": "get_recommendation_consistency",
        "description": "检查推荐列表排序一致性（是否严格按 recommended_score 降序）。",
        "method": "GET",
        "path": "/api/recommendations/consistency",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/recommendations/consistency",
    },
    {
        "name": "get_system_health",
        "description": "获取系统健康汇总：LLM 状态、存储、摘要、Outbox、备份状态。",
        "method": "GET",
        "path": "/api/system-health",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "example": "GET /api/system-health",
    },
]

VERSION = "mcp-tools-v1"


def manifest():
    """Return the MCP-compatible tool registry."""
    return {
        "version": VERSION,
        "protocol": "rest-bridge",
        "description": "RSS AI Worker 只读工具集。所有工具均为只读查询，不修改 Miniflux 文章状态，不开启自动动作。",
        "authentication": "HTTP Basic Auth（控制台同款凭据）",
        "base_url": "http://<host>:18090",
        "tools": TOOLS,
    }
