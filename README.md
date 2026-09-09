<div align="center">

# ⚡ FluxPilot

**新一代全自动 RSS 智能信息流基础设施**  
*FluxPilot: All-in-One Autonomous RSS Intelligence & Clean Reading Infrastructure*

[![Docker Multi-Arch](https://img.shields.io/badge/Docker-Multi--Arch%20(amd64%20%7C%20arm64)-blue?logo=docker)](https://github.com/ailiksr/FluxPilot)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-yellow?logo=python)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-blue?logo=postgresql)](https://postgresql.org)
[![Miniflux](https://img.shields.io/badge/Miniflux-v2.2.3-orange?logo=rss)](https://miniflux.app)

<p align="center">
  <b>彻底告别信息过载与手动打分标注</b><br>
  集成了 <b>Miniflux 官方核心</b> + <b>Reactflux 沉浸阅读器</b> + <b>AI 自主研判与自愈中枢</b> + <b>防盗链图片代理</b>。<br>
  宏观由你定规则，微观由 AI 自动分流，让信息消费重归纯粹与高效。
</p>

</div>

---

## ✨ 核心特性一览 (Key Highlights)

### 1. ⚡ 前置启发式规则熔断网关 (Pre-LLM Fast-Path)
- **0 Token 消耗、纳秒级拦截**：在文章进入大模型之前，通过特征树与正则在本地阻断明显促销导购、极端垃圾水文；
- **白名单绝对保护**：命中关注词与技术主题的文章强制放行至大模型全文精读，严防误杀；
- **节约 40%+ 算力**：跳过后续评分与大模型总结，大幅降低 API 调用费用与排队等待。

### 2. 🎯 偏好与过滤规则引擎 (Feedly Leo & newscope 模式)
- **宏观规则调控，告别微观打工人**：支持设定关注词 (Boost +15分)、绝对屏蔽词 (Hard Mute)、轻度降权词 (Soft Demote -15分) 与内容类型开关；
- **文末防暗广穿透扫描**：即使标题伪装成干货，文末 500 字挂载的淘客群、返利链接也能被精准探测捕获；
- **💡 AI 规则智能挖掘**：从历史文章池自动反向挖掘高频垃圾词与升温技术主题，界面一键气泡采纳；
- **🧪 实时测算沙箱与防误杀预警**：输入规则词时实时模拟匹配篇数，若可能误伤高分好文，立即弹出黄色警示框。

### 3. 📖 Reactflux 原生沉浸提纯阅读 (Zero Duplication)
- **零文章克隆、零套娃订阅**：完全基于 Miniflux 原生文章唯一 ID，阅读进度与状态 100% 实时同步；
- **⭐ 高分自动标星 (Auto-Starred)**：AI 评分 ≥75 分的好文自动标星，打开 Reactflux 收藏夹即可阅读全网硬核好文；
- **🗑️ 垃圾自动隐形沉底 (Auto-Silence)**：营销与低质文章自动标已读，从未读流中彻底消失；
- **🧠 正文 AI 研判透明折叠卡片 (Decision Inspector)**：
  - 文章正文顶部内嵌原生 `<details>` 研判折叠卡片（免脚本、全端自适应）；
  - 呈现研判路径、分值拆解、多维量化依据（信息/深度/原创/营销）以及点词成规快捷键。

### 4. 🩺 订阅源自动诊断与自愈引擎 (Self-Healing Feeds)
- **超时协议自愈降级**：检测到首包超时或握手卡死，自动为该源关闭 HTTP/2 回退 HTTP/1.1；
- **防爬拦截自愈**：检测到 403 Forbidden 或 Cloudflare 拦截，自动注入桌面级 Chrome 浏览器 UA 仿生；
- **休眠自动解冻**：源站恢复通畅后，自动解除 Miniflux 的挂起禁用状态；
- **断路器保护**：24 小时限额重试，避免死循环修改配置。

### 5. 🎛️ 现代化四大工作台运营控制台 (Operations Console)
- **极速键盘流**：数字键 `1` / `2` / `3` / `4` 快速切页，`r` 键触发全局刷新，`Esc` 关闭弹窗；
- **Tab 1: 待办与清理**：待裁决边界文章置顶，支持 **一键全部保留/丢弃**；废纸篓支持分类胶囊过滤与一键清空；
- **Tab 2: 偏好与规则**：标签即时搜索过滤、一键清理 0 命中废词、规则导出与导入备份；
- **Tab 3: 订阅源治理**：多维度源搜索、状态过滤、实时展开自愈巡检诊断日志；
- **Tab 4: 探索与系统**：全文搜索、全网动量趋势图、算力节约大屏与容器自治运维监控。

### 6. 🤖 外部 AI 助手接入 (Model Context Protocol / MCP)
- 内置 18 个标准只读查询工具，支持通过 HTTP REST API 无缝接入 Claude Desktop、Cursor 等外部 AI 客户端。

---

## 🚀 1 分钟快速启动 (Quick Start)

### 1. 准备配置文件
下载生产编排文件并复制配置模板：
```bash
mkdir -p fluxpilot && cd fluxpilot
curl -fsSL https://raw.githubusercontent.com/ailiksr/FluxPilot/main/compose.yml -o compose.yml
curl -fsSL https://raw.githubusercontent.com/ailiksr/FluxPilot/main/.env.example -o .env
```

### 2. 配置环境变量
编辑 `.env` 文件，填入你的大模型 API 密钥与管理员密码：
```bash
# 必填项：大模型 API（支持 OpenAI、DeepSeek、Ollama 等）
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-llm-api-key
AI_MODEL=gpt-4o-mini

# 数据库与管理密码
MINIFLUX_ADMIN_PASSWORD=your_secure_password
POSTGRES_PASSWORD=your_secure_postgres_password
```

### 3. 一键启动
```bash
docker compose up -d
```
全套容器采用云端预构建的多架构镜像（`linux/amd64` 与 `linux/arm64`），**无需本地编译 Python 依赖，10 秒内即可拉取并健康就绪！**

### 4. 访问入口
- 📖 **Reactflux 现代阅读器**：`http://localhost:13000`
- 🎛️ **AI 运营控制台**：`http://localhost:18090/ai-worker`
- ⚙️ **Miniflux 官方管理端**：`http://localhost:18080`
- 📰 **AI 高分精选源**：`http://localhost:18090/rss/curated?min_score=70`

---

## 🏛️ 系统架构 (Architecture)

```text
                  外部 RSS 源 (Atom / RSS / JSON)
                               │
                               ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Miniflux 核心引擎 (Go) ── 抓取、全文解析、Webhook 通知      │
 └──────────────────────┬──────────────────────────────────────┘
                        │ (HTTP Webhook)
                        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ RSS AI Worker (Python 3.11 + Waitress WSGI)                 │
 │ ├── ⚡ Pre-LLM 启发式快速熔断网关 (Fast-Path Filter)          │
 │ ├── 🎯 宏观偏好与文末暗广穿透引擎 (Rules Store & Miner)     │
 │ ├── 🤖 大模型六维价值评分体系 (Continuous Scoring V23)       │
 │ ├── 📝 高分好文自适应深度解析摘要 (Adaptive Deep Brief)       │
 │ ├── 🩺 订阅源自动诊断与自愈管家 (Self-Healing Feeds)         │
 │ └── 🛡️ 容器内置存储自洽巡检 (In-Container Storage Patrol)   │
 └──────────────────────┬──────────────────────────────────────┘
                        │ (Miniflux REST API)
                        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 统一存储与展现层                                             │
 │ ├── PostgreSQL 17 (双 Schema 物理隔离: public + control)     │
 │ ├── Reactflux Web (自动标星 + 自动沉底 + 决策透明卡片)      │
 │ └── Image Proxy (防盗链多级缓存图片代理)                    │
 └─────────────────────────────────────────────────────────────┘
```

---

## 🔄 自动化更新 (Watchtower & Portainer 部署)

### 方案 A：使用 Watchtower 全自动静默更新 (推荐)
本项目镜像预置了 Watchtower 标签支持，仅对业务层（`miniflux-ai` 和 `image-proxy`）进行平滑自动更新，同时保护底层 PostgreSQL 数据库不被盲目重启：
```yaml
# 在宿主机运行 Watchtower
docker run -d \
  --name watchtower \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --interval 3600 \
  --cleanup \
  --label-enable
```
当云端发布新版本时，Watchtower 将自动拉取新镜像并平滑重启业务容器，**所有数据与自愈规则完好继承，零人工介入**。

### 方案 B：在 Portainer Stacks 中原生自动更新
在 Portainer 中新建 Stack 时：
1. 部署模式选择 **Repository (Git)**；
2. 填入仓库地址：`https://github.com/ailiksr/FluxPilot`；
3. Compose 路径填入：`compose.yml`；
4. 开启 **Automatic Updates**（定时轮询或配置 Webhook），GitHub 有新更新时 Portainer 自动重构拉取！

---

## 🛠️ 本地二次开发 (Development)

若你需要基于源码进行本地构建与二次开发，可以使用开发覆盖文件：
```bash
# 本地编译镜像并启动
docker compose -f compose.yml -f compose.build.yml up -d --build

# 运行全量单元测试套件 (255 项全自动化测试)
cd miniflux-ai
docker build -t rss-ai-test -f Dockerfile.test .
docker run --rm rss-ai-test pytest -q
```

---

## 🤝 致谢与上游开源项目 (Acknowledgements)

本项目站在了诸多优秀开源项目与理念巨人的肩膀上，在此由衷致谢：

- **[Miniflux](https://miniflux.app/)** by *Frédéric Guillot* (Apache-2.0 License) —— 坚如磐石、轻量且具备全功能 API 的核心 RSS 抓取基石；
- **[serpicroon/miniflux-ai](https://github.com/serpicroon/miniflux-ai)** (MIT License) —— 本项目 AI Worker 的最初架构灵感与开发基础；
- **[electh/reactflux](https://github.com/electh/reactflux)** (MIT License) —— 优雅高效的第三方现代 Web 阅读客户端；
- **产品理念致谢**：参考了 **Feedly Leo**（优先主题与静音过滤器）、**Inoreader Rules**（规则测算与沙箱预警）以及 **FreshRSS**（订阅源故障修复）的设计哲学。

---

## 📄 开源许可证 (License)

本项目采用 [MIT License](LICENSE) 授权开源。
商业与个人使用均友好，欢迎提交 Issue 与 Pull Request！
