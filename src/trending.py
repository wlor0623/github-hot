"""抓取并解析 github.com/trending 页面（无官方 API）。

⚠ 页面 HTML 结构变化时只需修改本文件的 parse() 选择器。
"""

import re

import requests
from bs4 import BeautifulSoup

TRENDING_URL = "https://github.com/trending"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _num(el) -> int:
    """提取元素文本里的第一个整数（'1,234 stars today' -> 1234）。"""
    if el is None:
        return 0
    m = re.search(r"[\d,]+", el.get_text())
    return int(m.group().replace(",", "")) if m else 0


def parse(html: str) -> list[dict]:
    """解析 trending 页面，返回榜单条目列表；解析到 0 条视为结构失效。"""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for rank, art in enumerate(soup.select("article.Box-row"), 1):
        link = art.select_one("h2 a")
        if not link or not link.get("href"):
            continue
        full_name = link["href"].strip("/")
        desc_el = art.select_one("p")
        lang_el = art.select_one('[itemprop="programmingLanguage"]')

        stars = forks = 0
        for a in art.select("a.Link--muted"):
            svg = a.find("svg")
            cls = " ".join(svg.get("class", [])) if svg else ""
            if "octicon-star" in cls:
                stars = _num(a)
            elif "octicon-repo-forked" in cls:
                forks = _num(a)

        period_el = art.select_one("span.d-inline-block.float-sm-right")
        avatar_el = art.select_one("img.avatar") or art.select_one("img")

        items.append({
            "rank": rank,
            "full_name": full_name,
            "url": f"https://github.com/{full_name}",
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "language": lang_el.get_text(strip=True) if lang_el else None,
            "stars": stars,
            "forks": forks,
            "period_stars": _num(period_el),
            "avatar": avatar_el.get("src", "") if avatar_el else "",
        })
    if not items:
        raise ValueError("trending 页面解析到 0 条，页面结构可能已变化")
    return items


def fetch_one(since: str = "daily", language: str = "") -> list[dict]:
    """抓取单个榜单。language 为 trending URL slug，空串表示全站。"""
    url = TRENDING_URL + (f"/{language}" if language else "")
    resp = requests.get(url, params={"since": since}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse(resp.text)


def fetch_all(cfg: dict) -> dict:
    """抓取配置里所有 榜期×语言 组合，返回 {"daily": {"": [...], "python": [...]}, ...}。"""
    board: dict = {}
    for since in cfg.get("trending_sinces", ["daily", "weekly"]):
        board[since] = {}
        for slug in cfg.get("languages", [""]):
            board[since][slug] = fetch_one(since=since, language=slug)
    return board
