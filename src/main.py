"""入口编排：python -m src.main [--mode daily|sample|auto] [--dry-run]

- daily：Trending 抓取 → 雷达搜索 → star 增量计算 → 快照/日报落盘 → 推送
- sample：仅对跟踪仓库采样 star 并更新状态；出现涨速告警时推送短消息
- --dry-run：只写本地文件，不推送（提交由 workflow 的 git 步骤负责）
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src import config, gh_api, notify, radar as radar_mod, report, tracker, trending as trending_mod

ROOT = config.ROOT
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
TZ = ZoneInfo("Asia/Shanghai")


def resolve_mode(mode_arg: str) -> str:
    """auto 模式：按 workflow 触发时的 cron 判断（全量 cron 见 config.DAILY_CRON）。"""
    if mode_arg != "auto":
        return mode_arg
    schedule = os.environ.get("TRIGGERED_SCHEDULE", "")
    return "daily" if schedule == config.DAILY_CRON else "sample"


def _collect_meta(board: dict, radar_items: list) -> dict:
    """从榜单与雷达结果合并 {full_name: {description, language}} 元数据。"""
    metas = {}
    for since_items in board.values():
        for items in since_items.values():
            for it in items:
                metas.setdefault(it["full_name"], {
                    "description": it.get("description", ""),
                    "language": it.get("language"),
                })
    for it in radar_items:
        metas.setdefault(it["full_name"], {
            "description": it.get("description", ""),
            "language": it.get("language"),
        })
    return metas


def run_daily(cfg: dict, dry_run: bool) -> dict:
    warnings: list[str] = []
    client = gh_api.GitHubClient()
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")
    generated_at = now.isoformat(timespec="seconds")

    # 1) Trending（失败自动降级）
    board = {}
    try:
        board = trending_mod.fetch_all(cfg)
        total = sum(len(v) for s in board.values() for v in s.values())
        print(f"[trending] 抓取 {total} 条")
    except Exception as e:
        warnings.append(f"trending: {type(e).__name__}: {e}")
        print(f"[trending] 失败，降级为无榜单: {e}")

    # 2) 新项目雷达（失败自动降级）
    radar_items = []
    try:
        radar_items = radar_mod.search(client, cfg)
        print(f"[radar] 发现 {len(radar_items)} 个新项目")
    except Exception as e:
        warnings.append(f"radar: {type(e).__name__}: {e}")
        print(f"[radar] 失败，降级: {e}")

    # 3) star 采样与增量（跟踪集 = 存量 ∪ 榜单 ∪ 雷达）
    metas = _collect_meta(board, radar_items)
    state = tracker.load(DATA_DIR)
    names = sorted(set(state["repos"]) | set(metas))
    print(f"[tracker] 拉取 {len(names)} 个仓库的 star …")
    current = client.fetch_stars(names)
    ok_count = sum(1 for v in current.values() if v)
    print(f"[tracker] 成功 {ok_count}/{len(names)}")

    gains = tracker.compute_deltas(state, current)
    threshold = cfg["surge"]["daily_threshold"]
    surges = [g for g in gains if g["delta_24h"] is not None and g["delta_24h"] >= threshold]

    # 4) 更新并保存状态（榜单/雷达出现过的仓库刷新 last_seen）
    new_state = tracker.update(state, current, set(metas), cfg["track_retention_days"], date_str, metas)
    for g in gains:  # 用最新元数据补全涨幅条目
        rec = new_state["repos"].get(g["full_name"])
        if rec:
            g["description"] = rec.get("description", "")
            g["language"] = rec.get("language")
    tracker.save(DATA_DIR, new_state)

    # 5) 摘要与日报
    digest_text = report.build_digest(cfg, board.get("daily", {}).get("", []),
                                      radar_items, gains, surges, date_str)
    md_text = report.build_markdown(cfg, date_str, generated_at, board, radar_items,
                                    gains, surges, len(new_state["repos"]), warnings)

    snapshot = {
        "date": date_str,
        "generated_at": generated_at,
        "trending": board,
        "radar": radar_items,
        "gainers": [g for g in gains if g["delta_24h"] is not None][:50],
        "surges": surges,
        "stars_sample": {n: i["stars"] for n, i in current.items() if i},
        "tracked": sorted(new_state["repos"]),
        "digest": digest_text,
        "warnings": warnings,
    }
    snap_dir = DATA_DIR / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    with open(snap_dir / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / f"{date_str}.md", "w", encoding="utf-8") as f:
        f.write(md_text)

    # 6) 推送
    notify_results = []
    if not dry_run:
        notify_results = notify.send_all(digest_text, title=f"GitHub 热门日报 {date_str}",
                                         channels=cfg.get("notify"))
        for r in notify_results:
            print(f"[notify] {r['channel']}: {'OK' if r['ok'] else 'FAIL ' + r['detail']}")
    else:
        print("[notify] dry-run 跳过推送")

    return {"mode": "daily", "date": date_str, "tracked": len(new_state["repos"]),
            "surges": len(surges), "warnings": warnings}


def run_sample(cfg: dict, dry_run: bool) -> dict:
    client = gh_api.GitHubClient()
    now = datetime.now(TZ)
    state = tracker.load(DATA_DIR)
    names = sorted(state["repos"])
    print(f"[tracker] 采样 {len(names)} 个仓库 …")
    current = client.fetch_stars(names)

    gains = tracker.compute_deltas(state, current)
    threshold = cfg["surge"]["daily_threshold"]
    surges = [g for g in gains if g["delta_24h"] is not None and g["delta_24h"] >= threshold]

    tracker.update(state, current, set(), cfg["track_retention_days"], now.strftime("%Y-%m-%d"))
    tracker.save(DATA_DIR, state)

    if surges and not dry_run:
        alert = report.build_alert(cfg, surges, now.strftime("%m-%d %H:%M"))
        for r in notify.send_all(alert, title="⚡ GitHub 涨速告警", channels=cfg.get("notify")):
            print(f"[notify] {r['channel']}: {'OK' if r['ok'] else 'FAIL ' + r['detail']}")
    elif surges:
        print(f"[notify] dry-run 跳过告警推送（{len(surges)} 条）")

    return {"mode": "sample", "date": now.strftime("%Y-%m-%d"),
            "sampled": sum(1 for v in current.values() if v), "surges": len(surges)}


def main():
    parser = argparse.ArgumentParser(description="GitHub 热门项目监控")
    parser.add_argument("--mode", choices=["daily", "sample", "auto"], default="auto",
                        help="daily=全量 sample=仅采样 auto=按触发 cron 判断（默认）")
    parser.add_argument("--dry-run", action="store_true", help="只写本地文件，不推送")
    args = parser.parse_args()

    cfg = config.load()
    mode = resolve_mode(args.mode)
    print(f"=== github-hot monitor · mode={mode} · dry_run={args.dry_run} ===")

    summary = run_daily(cfg, args.dry_run) if mode == "daily" else run_sample(cfg, args.dry_run)
    print("=== 完成:", json.dumps(summary, ensure_ascii=False), "===")


if __name__ == "__main__":
    main()
