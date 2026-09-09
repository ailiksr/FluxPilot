# AI 助手接入指南（MCP 桥接）

本项目提供 **rest2mcp 式轻量 MCP 桥接**——无需安装任何额外依赖，外部 AI 助手（Claude Desktop、Cursor、任何 MCP 客户端）可通过 HTTP 直接调用 AI Worker 的只读查询能力。

## 快速接入

### 1. 获取工具清单

```bash
# 列出所有可用工具（携带控制台 Basic Auth 凭据）
curl -u admin:password http://<SERVER_IP>:18090/api/mcp/manifest
```

返回 18 个只读工具：

| 工具 | 作用 | 推荐场景 |
|------|------|---------|
| `get_scores` | 所有已评分文章及 AI 判断 | 了解当前内容质量分布 |
| `get_recommendations` | AI 推荐列表（含 Feed 权重） | 获取推荐阅读 |
| `get_trends` | 主题热度/关键词/类型分布 | 了解近期热点 |
| `get_feed_health` | 各 Feed 抓取成功率/延迟 | 检查 RSS 源稳定性 |
| `get_feed_health_trends` | 24h 成功率/延迟时间序列 | 排查抓取异常 |
| `get_feed_quality` | 各 Feed 内容质量分析 | 评估 RSS 源价值 |
| `get_feed_policy` | AI 推荐权重配置 | 查看 Feed 优先级 |
| `get_autonomous_decisions` | AI 自主分流统计 | 了解 AI 自动处理情况 |
| `get_preference_profile` | 用户偏好画像 | 了解兴趣偏好 |
| `get_backtest` | Shadow 回测结果 | 评估自动路由准确率 |
| `get_benchmark_pending` | 待人工审核队列 | 检查需要人工处理的文章 |
| `get_archive_review` | 归档复审候选 | 检查待归档文章 |
| `get_article_detail` | 单篇文章详情 | 深入查看 AI 判断 |
| `get_system_status` | 系统运行状态 | 快速诊断 |
| `get_console_summary` | 控制台摘要 | 整体概览 |
| `search_articles` | 全文搜索文章 | 查找特定内容 |
| `get_recommendation_consistency` | 推荐排序一致性 | 验证排序正确性 |
| `get_system_health` | 系统健康汇总 | 运维检查 |

### 2. 调用工具

所有工具都是 `GET` 请求，携带与 AI Worker 控制台相同的 Basic Auth 凭据：

```bash
# 示例：搜索文章
curl -u admin:password "http://<SERVER_IP>:18090/api/search?q=AI&limit=5"

# 示例：获取趋势分析
curl -u admin:password "http://<SERVER_IP>:18090/api/scoring/trends"

# 示例：获取系统健康
curl -u admin:password "http://<SERVER_IP>:18090/api/system-health"
```

### 3. Claude Desktop 配置

在 Claude Desktop 的 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "rss-ai-worker": {
      "type": "http",
      "url": "http://<SERVER_IP>:18090/api/mcp/manifest",
      "headers": {
        "Authorization": "Basic <base64-encoded-credentials>"
      }
    }
  }
}
```

其中 `<base64-encoded-credentials>` 是 `控制台用户名:密码` 的 Base64 编码：

```bash
echo -n "admin:你的密码" | base64
```

### 4. Cursor 配置

在 Cursor 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "rss-ai-worker": {
      "type": "http",
      "url": "http://<SERVER_IP>:18090/api/mcp/manifest",
      "headers": {
        "Authorization": "Basic <base64-encoded-credentials>"
      }
    }
  }
}
```

### 5. 编程调用（Python 示例）

```python
import requests

BASE = "http://<SERVER_IP>:18090"
AUTH = ("admin", "你的密码")

# 获取工具清单
manifest = requests.get(f"{BASE}/api/mcp/manifest", auth=AUTH).json()
print(f"可用工具: {len(manifest['tools'])} 个")

# 搜索文章
results = requests.get(f"{BASE}/api/search?q=AI&limit=5", auth=AUTH).json()
for item in results["items"]:
    print(f"  [{item['ai_score']}] {item['title']}")

# 获取趋势
trends = requests.get(f"{BASE}/api/scoring/trends", auth=AUTH).json()
print(f"热门主题: {[t['topic'] for t in trends['topic_trends'][:5]]}")
```

## 安全说明

- 所有工具均为**只读**，不修改 Miniflux 文章状态，不开启自动归档
- 携带与 AI Worker 控制台相同的 Basic Auth 凭据（`RSS_AI_ADMIN_USER` / `RSS_AI_ADMIN_PASSWORD`）
- 凭据切勿明文写入公开文档或版本库
- 建议在局域网内使用，不要暴露到公网