# miniflux-ai — RSS AI Worker & Operations Console

[![GitHub license](https://img.shields.io/github/license/serpicroon/miniflux-ai)](https://github.com/serpicroon/miniflux-ai/blob/main/LICENSE)

> **Transform your RSS feed into an intelligent, AI-curated information hub.**

基于 [Miniflux](https://miniflux.app/) 的 AI RSS Worker：LLM 评分、自主分流、人工复审、Feed 健康监控，并提供完整的管理控制台与 MCP 工具桥接。

---

## 🏗️ 系统架构

```text
RSS Feed 源
    ↓ 抓取
Miniflux (PostgreSQL 文章真源)
    ↓ Webhook/轮询
AI Worker (LLM Judge → 评分 → 自主分流)
    ↓ PostgreSQL 事务写入 (rss_ai_control)
    ↓ Outbox → JSONL 备份导出
运营控制台 (:18090/ai-worker)
    ├─ 系统概览 / Feed 健康 / Feed 质量 / Feed 策略
    ├─ AI 决策中心 / 自动化准备度 / 偏好画像
    ├─ 文章信号 / 趋势分析 / 文章搜索
    ├─ 归档复审 / 运行审计
    └─ AI 助手接入 (MCP 工具清单)
Image Proxy (图片代理 :18091)
Reactflux (日常阅读 :13000)
```

### 服务组成

| 服务 | 职责 |
|------|------|
| **PostgreSQL** | Miniflux 文章/阅读状态真源 + AI 控制面数据 (`rss_ai_control` schema) |
| **Miniflux** | RSS 抓取、全文提取、搜索、阅读状态、Webhook |
| **AI Worker** | LLM Judge、评分、摘要、自主分流、Feed 健康、控制台 API |
| **Image Proxy** | 外部图片代理、SSRF 防护、缓存 |
| **Reactflux** | 日常 RSS 阅读界面 |

---

## ✨ 核心能力

### 1. AI 评分系统（V23 连续评分）
- **6 维质量判断**：信息增量、证据质量、内容深度、时效性、原创性、实用性
- **辅助负向维度**：营销、纯娱乐、低内容（软扣分，不归零）
- **固定锚点校准**：0→10、1.25→30、2.5→50、3.75→70、5→90（跨批次可比较）
- **确定性校准器**：LLM Judge 与 Score Engine 完全解耦，公式升级不重复调用 LLM

### 2. AI 自主分流
- 高价值/高兴趣 → 优先阅读；一般 → 正常保留；低质量/高营销/重复 → 建议跳过；信号冲突 → 边界复核
- **默认只影响排序和建议，不修改 Miniflux 文章状态**

### 3. 人工审核与安全边界
- 仅归档候选进入人工复审；普通文章由 AI 自动处理
- 人工审核决策（保留/忽略/标记归档）→ 偏好学习 → Shadow 回测
- **自动归档/删除默认关闭**，必须人工显式确认并支持撤销

### 4. 运营控制台（:18090/ai-worker）
14 个区块覆盖：系统概览、AI 决策、自动化准备度、偏好画像、文章信号、趋势分析、搜索、Feed 健康/质量/策略、AI 策略、归档复审、运行审计、MCP 接入。

### 5. 数据可靠性
- PostgreSQL 事务写入 + Outbox 模式 + JSONL 备份导出 + 一致性校验
- 每日备份（14 天保留）、SHA-256 校验、隔离恢复演练
- Feed 健康每 10 分钟采样（30 天窗口）

### 6. AI 助手接入（MCP 桥接）
- `GET /api/mcp/manifest`：15 个只读工具清单（评分/推荐/趋势/Feed 健康/偏好画像等）
- 零新依赖的 rest2mcp 式桥接，外部 AI 助手可通过既有 REST API 查询

### 7. 精选文章 Feed
- `GET /rss/curated?min_score=70&limit=30`：AI 评分筛选的高价值文章 RSS，供任何阅读器订阅

---

## 🚀 快速开始

### 环境要求
- Docker + Docker Compose
- LLM API（OpenAI 兼容端点）

### 部署
```bash
# 1. 配置 .env（含 Miniflux 管理员账号、LLM API key、LAN IP）
cp .env.example .env

# 2. 启动全部服务
docker compose up -d

# 3. 访问
# 运营控制台: http://<LAN_IP>:18090/ai-worker
# Miniflux 阅读: http://<LAN_IP>:18080
# Reactflux 阅读: http://<LAN_IP>:13000
# Image Proxy 健康: http://<LAN_IP>:18091/healthz
```

---

## 🔌 配置

参考配置文件：
- **[config.sample.English.yml](config.sample.English.yml)** - English
- **[config.sample.Chinese.yml](config.sample.Chinese.yml)** - 中文

关键环境变量（`.env`）：
```text
MINIFLUX_ADMIN_USER / MINIFLUX_ADMIN_PASSWORD  控制台 Basic Auth + Miniflux 管理员
LAN_IP                                          服务绑定地址
LLM base_url / api_key / model                  评分与摘要模型
RSS_AI_STORAGE_MODE / RSS_AI_WRITE_MODE         postgres / jsonl
```

---

## 🧠 自定义 Agent

内置摘要/翻译 Agent，可自定义更多处理 Agent（如"市场分析师"、"TL;DR"）：

```yaml
agents:
  analyst:
    prompt: "Analyze this article for potential stock market impacts."
    template: '<div class="insight-box">📈 <strong>Market Impact:</strong> {content}</div>'
    deny_rules:
      - EntryTitle=(?i)(advertisement|sponsored)
    allow_rules:
      - FeedSiteURL=.*bloomberg\.com.*
```

规则格式：`FieldName=RegexPattern`，支持标题/URL/内容/作者/Feed 等字段，以及内容长度数值运算（`gt:`/`lt:`/`between:`）。

---

## 🔧 常见问题

<details>
<summary><strong>控制台页面样式错乱？</strong></summary>
按 Ctrl+Shift+R 强制刷新（资源带版本号缓存）。若仍异常，检查容器内 `/app/app/static/css/console.css` 是否存在。
</details>

<details>
<summary><strong>镜像构建卡住？</strong></summary>
当前使用 Debian slim 基镜像（lxml/tiktoken 有预编译 wheel，无需 gcc）。不要用 `docker buildx prune -f` 清缓存（会导致依赖层重新下载）。
</details>

<details>
<summary><strong>修改代码后页面没变？</strong></summary>
生产容器使用固定镜像，必须重新 `docker compose build miniflux-ai && docker compose up -d --force-recreate miniflux-ai`。仅 restart 不会加载宿主机源码。
</details>

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 📚 运维交接

生产运维细节、评分系统演进、安全边界与下一步规划见 **`/opt/rss-ai/AI_HANDOVER.md`**（项目内权威文档）。
