"""Star 涨速追踪：state.json 状态管理 + 6h/24h 增量计算 + 告警判定。

state.json 结构：
    {"updated_at": ..., "repos": {"owner/name": {
        "first_seen": "2026-11-22", "last_seen": "2026-11-22",
        "stars": 12345, "avatar": "...",
        "samples": [{"ts": iso, "stars": int}, ...]   # 最近 8 次采样，覆盖 48h
    }}}
"""

import json
from datetime import datetime, timedelta, timezone

from pathlib import Path

# 每仓库保留的采样点数（6h 采样一次 → 覆盖 48h，足够算 24h 增量）
SAMPLES_KEEP = 8

# 24h 增量取样的目标窗口：优先取 20~28h 前的采样点
D24_MIN_HOURS = 20


def state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def load(data_dir: Path) -> dict:
    path = state_path(data_dir)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": None, "repos": {}}


def save(data_dir: Path, state: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(state_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def compute_deltas(state: dict, current: dict) -> list[dict]:
    """对比当前采样与历史采样，返回涨幅条目列表（按 24h 增量降序）。

    current: {full_name: {"stars": int, "avatar": ...} | None}（None = 拉取失败）
    首次运行没有历史采样时 delta 为 None，条目仍保留 stars 基础信息。
    """
    now = datetime.now(timezone.utc)
    gains = []
    for name, info in current.items():
        if not info:
            continue
        stars = info["stars"]
        rec = state["repos"].get(name) or {}
        samples = rec.get("samples") or []
        d6 = d24 = None
        window_hours = None
        if samples:
            d6 = stars - samples[-1]["stars"]
            # 24h 基准点：最早的采样里找一个落在 20h 前之前的；找不到就取最早一条
            base = samples[0]
            for s in samples:
                ts = datetime.fromisoformat(s["ts"])
                if (now - ts).total_seconds() / 3600 >= D24_MIN_HOURS:
                    base = s
                    break
            d24 = stars - base["stars"]
            window_hours = round((now - datetime.fromisoformat(base["ts"])).total_seconds() / 3600, 1)
        gains.append({
            "full_name": name,
            "url": f"https://github.com/{name}",
            "stars": stars,
            "delta_6h": d6,
            "delta_24h": d24,
            "window_hours": window_hours,
            "avatar": info.get("avatar", "") or rec.get("avatar", ""),
            "description": rec.get("description", ""),
            "language": rec.get("language"),
        })
    gains.sort(key=lambda g: (g["delta_24h"] is None, -(g["delta_24h"] or 0)))
    return gains


def update(state: dict, current: dict, seen_names: set[str],
           retention_days: int, today: str, meta_by_name: dict | None = None) -> dict:
    """写入本次采样并维护状态：更新 last_seen / 描述 / 采样队列，裁剪过期仓库。"""
    repos = state["repos"]
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metas = meta_by_name or {}

    for name, info in current.items():
        if not info:
            continue  # 拉取失败的仓库不更新采样，保留旧基准
        rec = repos.setdefault(name, {"first_seen": today, "last_seen": today, "samples": []})
        if name in seen_names:
            rec["last_seen"] = today
        meta = metas.get(name) or {}
        if meta.get("description"):
            rec["description"] = meta["description"]
        if meta.get("language"):
            rec["language"] = meta["language"]
        rec["stars"] = info["stars"]
        rec.setdefault("avatar", "")
        if info.get("avatar"):
            rec["avatar"] = info["avatar"]
        samples = rec.setdefault("samples", [])
        samples.append({"ts": now_iso, "stars": info["stars"]})
        rec["samples"] = samples[-SAMPLES_KEEP:]

    # 长期未出现的仓库移出跟踪（防止无限膨胀）
    today_dt = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    expired = [n for n, r in repos.items()
               if (today_dt - datetime.strptime(r.get("last_seen", today), "%Y-%m-%d").replace(tzinfo=timezone.utc)).days > retention_days]
    for n in expired:
        del repos[n]

    state["updated_at"] = now_iso
    return state
