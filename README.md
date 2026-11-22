# github-hot — GitHub 热门项目监控

全自动监控 GitHub 热门项目：跑在 GitHub Actions 云端（免费、不依赖本机开机），结果通过 **网页报告站 + 仓库内日报 + 消息推送** 三路输出。

## 监控什么

| 模块 | 说明 |
|---|---|
| 🔥 **Trending 榜单镜像** | 抓取 github.com/trending 的日榜/周榜（全站 + Python/TypeScript/Rust/Go 等分语言） |
| 🚀 **新项目雷达** | 官方 Search API 找「最近 7 天创建且 star 已 ≥50」的新仓库，发现刚冒头的新星 |
| 📈 **Star 涨速追踪** | 每 6 小时采样所有跟踪仓库的 star，计算 24h 增量；单日涨幅超过阈值（默认 500）触发 ⚡ 告警——在它上 trending 之前发现苗头 |

跟踪集合自动增长：上榜 ∪ 雷达发现的仓库都会被跟踪，30 天未再出现自动移出。

## 输出到哪

- **网页报告站**：<https://wlor0623.github.io/github-hot/> —— 今日三榜 + 任意仓库 star 历史曲线 + 历史存档
- **仓库内日报**：[reports/](reports/) 每天一份 Markdown；[data/snapshots/](data/snapshots/) 每天一份 JSON 快照
- **消息推送**：飞书 / 钉钉 / 企业微信群机器人（Secrets 里配了哪个推哪个）

## 架构

```
.github/workflows/monitor.yml      # 唯一工作流
  ├─ 每天 08:00 (北京时间) 全量：Trending + 雷达 + star 采样 + 日报 + 推送 + 部署站点
  └─ 每天 14:00 / 20:00 / 02:00    仅 star 采样（保证 24h 涨幅是分段采样的准确值）

src/
  main.py       # 编排入口：--mode daily|sample，--dry-run 本地测试不推送不提交
  config.py     # 读 config.json
  gh_api.py     # REST 客户端（token / 重试 / 并发拉 star）
  trending.py   # 解析 trending 页 HTML（无官方 API；页面改版时只改这个文件）
  radar.py      # Search API 新项目雷达
  tracker.py    # star 状态管理 + 6h/24h 增量计算 + 告警判定
  notify.py     # 飞书 / 钉钉(支持加签) / 企业微信 webhook
  report.py     # 日报与推送摘要生成
  build_site.py # 组装 Pages 站点 public/（静态页 + 快照数据 + index.json）

site/           # 静态网页（ECharts 本地内嵌，无 CDN 依赖）
data/           # state.json（star 状态）+ snapshots/*.json（每日快照）——均提交入库
reports/        # 每日 Markdown 日报——提交入库
```

## 使用

### 云端（默认，无需维护）

推送本仓库后 Actions 自动按 cron 运行；也可在 **Actions → monitor → Run workflow** 手动触发（可选 `daily` / `sample` 模式）。

首次部署需启用 Pages：仓库 **Settings → Pages → Source 选 "GitHub Actions"**（一次性）。

### 本地手动跑

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows；Linux/macOS 用 .venv/bin/pip
.venv/Scripts/python -m src.main --mode daily --dry-run
```

`--dry-run` 只写 data/ 和 reports/，不推送不提交。本地访问 GitHub 不稳时先 `export HTTPS_PROXY=http://127.0.0.1:7890`。

### 配置（config.json）

| 字段 | 默认 | 说明 |
|---|---|---|
| `languages` | 全站 + 4 语言 | trending 分语言榜单，填 trending URL 里的语言 slug |
| `radar.days` / `min_stars` / `top` | 7 / 50 / 30 | 新项目雷达窗口与门槛 |
| `surge.daily_threshold` | 500 | 24h star 增量告警阈值 |
| `track_retention_days` | 30 | 跟踪仓库多少天未出现后移出 |
| `digest.*_top` | 10 | 日报/推送各榜取前 N |

### Secrets 清单（Settings → Secrets and variables → Actions）

| Secret | 必填 | 说明 |
|---|---|---|
| `GH_TOKEN` | 否 | PAT；不配则用 Actions 自带 GITHUB_TOKEN（REST 限 1000 次/小时，仓库多后建议配） |
| `FEISHU_WEBHOOK` | 否 | 飞书群机器人 Webhook 地址 |
| `DINGTALK_WEBHOOK` | 否 | 钉钉群机器人 Webhook 地址 |
| `DINGTALK_SECRET` | 否 | 钉钉机器人「加签」密钥（安全设置选加签时必配） |
| `WECOM_WEBHOOK` | 否 | 企业微信群机器人 Webhook 地址 |

> 钉钉机器人若用「自定义关键词」模式，推送内容含「GitHub 热门」字样，关键词配这个即可。

## 已知边界

- **第一天数据不全**：star 增量需要至少两次采样（6 小时）才有 6h 涨幅，跑满 24h 后完整
- **trending 页面改版**：解析选择器集中在 `src/trending.py`；解析失败自动降级（雷达 + 涨幅照常出日报），Actions 不会红
- **Actions 定时有漂移**（±15 分钟）：对监控场景无影响，可手动触发补偿
