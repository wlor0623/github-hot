"""日报与推送摘要生成：Markdown 报告落盘 + 纯文本推送摘要。"""

from datetime import datetime, timezone


def fmt_stars(n) -> str:
    """12345 -> 12.3k，890 -> 890"""
    if n is None:
        return "-"
    if n >= 1000:
        v = n / 1000
        return f"{v:.1f}k".replace(".0k", "k")
    return str(n)


def cut(text, limit=50) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:limit] + "…" if len(text) > limit else text


def _age_days(created_at: str) -> int:
    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return max(0, (datetime.now(timezone.utc) - dt).days)


def build_digest(cfg: dict, trending_daily: list, radar: list, gains: list,
                 surges: list, date_str: str) -> str:
    """生成纯文本推送摘要（三个 webhook 渠道共用，不使用 Markdown 语法）。"""
    digest_cfg = cfg["digest"]
    lines = [f"📊 GitHub 热门日报 {date_str}"]

    top_t = trending_daily[:digest_cfg["trending_top"]]
    if top_t:
        lines += ["", f"🔥 Trending 日榜 TOP{len(top_t)}（全站）"]
        for i, it in enumerate(top_t, 1):
            lines.append(f"{i}. {it['full_name']}  ★{fmt_stars(it['stars'])}（今日 +{it['period_stars']}）")
            if it.get("description"):
                lines.append(f"   {cut(it['description'], 50)}")

    top_r = radar[:digest_cfg["radar_top"]]
    if top_r:
        r = cfg["radar"]
        lines += ["", f"🚀 新项目雷达 TOP{len(top_r)}（近{r['days']}天 ★≥{r['min_stars']}）"]
        for i, it in enumerate(top_r, 1):
            lines.append(f"{i}. {it['full_name']}  ★{fmt_stars(it['stars'])}（{_age_days(it['created_at'])}天前创建）")
            if it.get("description"):
                lines.append(f"   {cut(it['description'], 50)}")

    top_g = [g for g in gains if g["delta_24h"] is not None][:digest_cfg["gainers_top"]]
    if top_g:
        lines += ["", f"📈 Star 涨幅 TOP{len(top_g)}（24h）"]
        for i, g in enumerate(top_g, 1):
            lines.append(f"{i}. {g['full_name']}  +{g['delta_24h']}（★{fmt_stars(g['stars'])}）")

    if surges:
        th = cfg["surge"]["daily_threshold"]
        lines += ["", f"⚡ 涨速告警（24h ≥ {th}）"]
        for g in surges[:10]:
            lines.append(f"- {g['full_name']} +{g['delta_24h']}")

    lines += ["", f"👉 完整榜单：{cfg['site_url']}"]
    return "\n".join(lines)


def build_alert(cfg: dict, surges: list, now_str: str) -> str:
    """采样模式下的涨速告警短消息。"""
    th = cfg["surge"]["daily_threshold"]
    lines = [f"⚡ GitHub 涨速告警 {now_str}", f"（24h star 增量 ≥ {th}）", ""]
    for g in surges[:10]:
        lines.append(f"- {g['full_name']}  +{g['delta_24h']}  ★{fmt_stars(g['stars'])}")
    return "\n".join(lines)


def build_markdown(cfg: dict, date_str: str, generated_at: str, board: dict,
                   radar: list, gains: list, surges: list, tracked_count: int,
                   warnings: list) -> str:
    """生成完整 Markdown 日报。"""
    digest_cfg = cfg["digest"]
    L = [f"# 📊 GitHub 热门日报 · {date_str}",
         "",
         f"> 生成时间：{generated_at} · 跟踪仓库 {tracked_count} 个 · [网页版]({cfg['site_url']})"]

    if warnings:
        L += ["", "> ⚠️ 部分数据源异常：" + "；".join(warnings)]

    def repo_table(rows, extra_header, extra_field, fmt_extra):
        out = ["| # | 仓库 | 语言 | Star | " + extra_header + " | 描述 |",
               "|---|---|---|---|---|---|"]
        for i, it in enumerate(rows, 1):
            out.append(
                f"| {i} | [{it['full_name']}]({it['url']}) "
                f"| {it.get('language') or '-'} | {fmt_stars(it.get('stars'))} "
                f"| {fmt_extra(it)} | {cut(it.get('description'), 40)} |"
            )
        return out

    # Trending
    for since in board:
        title = {"daily": "🔥 Trending 日榜", "weekly": "📈 Trending 周榜"}.get(since, since)
        L += ["", f"## {title}"]
        for slug, items in board[since].items():
            name = "全站" if not slug else slug
            L += ["", f"### {name}（TOP{digest_cfg['trending_top']}）", ""]
            L += repo_table(items[:digest_cfg["trending_top"]],
                            "增量", "period_stars", lambda it: f"+{it.get('period_stars', 0)}")

    # 雷达
    if radar:
        r = cfg["radar"]
        L += ["", f"## 🚀 新项目雷达（近 {r['days']} 天创建 · ★≥{r['min_stars']}）", ""]
        L += repo_table(radar[:digest_cfg["radar_top"]],
                        "创建", "created_at", lambda it: f"{_age_days(it['created_at'])} 天前")

    # 涨幅
    top_g = [g for g in gains if g["delta_24h"] is not None][:digest_cfg["gainers_top"]]
    if top_g:
        L += ["", "## 📈 Star 涨幅 TOP%d（24h）" % len(top_g), ""]
        L += ["| # | 仓库 | 语言 | Star | 24h | 6h | 描述 |", "|---|---|---|---|---|---|---|"]
        for i, g in enumerate(top_g, 1):
            d6 = "-" if g["delta_6h"] is None else f"+{g['delta_6h']}"
            L.append(f"| {i} | [{g['full_name']}]({g['url']}) | {g.get('language') or '-'} "
                     f"| {fmt_stars(g['stars'])} | +{g['delta_24h']} | {d6} | {cut(g.get('description'), 40)} |")

    # 告警
    if surges:
        th = cfg["surge"]["daily_threshold"]
        L += ["", f"## ⚡ 涨速告警（24h ≥ {th}）", ""]
        for g in surges:
            L.append(f"- **[{g['full_name']}]({g['url']})** 24h **+{g['delta_24h']}** → ★{fmt_stars(g['stars'])}"
                     + (f" · {cut(g.get('description'), 60)}" if g.get("description") else ""))

    if not any([board, radar, top_g]):
        L += ["", "（本次未采集到数据，请查看 Actions 日志）"]

    L += ["", "---", f"*追踪列表由 Trending 上榜 ∪ 雷达发现自动维护，{cfg['track_retention_days']} 天未出现自动移出。*"]
    return "\n".join(L)
