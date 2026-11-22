"""新项目雷达：官方 Search API 找「最近 N 天创建且 star 已达标」的新仓库。"""

from datetime import datetime, timedelta, timezone


def search(client, cfg: dict) -> list[dict]:
    radar = cfg.get("radar", {})
    days = radar.get("days", 7)
    min_stars = radar.get("min_stars", 50)
    top = radar.get("top", 30)

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"created:>{since} stars:>={min_stars}"
    data = client.get("/search/repositories", params={
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(top, 50),
    })
    return [{
        "full_name": it["full_name"],
        "url": it["html_url"],
        "description": (it.get("description") or "")[:200],
        "language": it.get("language"),
        "stars": it["stargazers_count"],
        "forks": it["forks_count"],
        "avatar": (it.get("owner") or {}).get("avatar_url", ""),
        "created_at": it["created_at"],
    } for it in data.get("items", [])]
