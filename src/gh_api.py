"""GitHub REST API 客户端：token 注入、限速退避重试、并发批量拉 star。"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API_BASE = "https://api.github.com"


class RateLimitError(Exception):
    """API 配额耗尽（重试无意义，应尽快停止剩余请求）。"""


class GitHubClient:
    def __init__(self):
        # GH_TOKEN（用户 PAT）优先，其次 Actions 自带的 GITHUB_TOKEN
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-hot-monitor",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, params: dict | None = None, retries: int = 3):
        """GET 请求：429/5xx/403 指数退避重试，最终失败抛异常。"""
        url = path if path.startswith("http") else API_BASE + path
        delay = 2
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException:
                if attempt == retries:
                    raise
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 200:
                return resp.json()
            # 配额耗尽：重试无意义，立即熔断
            if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                raise RateLimitError("GitHub API 配额耗尽（未配 token 时仅 60 次/小时）")
            # 限速 / 服务端抖动 → 退避重试；其余状态码直接报错
            if resp.status_code == 403 or resp.status_code == 429 or resp.status_code >= 500:
                if attempt == retries:
                    resp.raise_for_status()
                wait = int(resp.headers.get("Retry-After") or 0) or delay
                time.sleep(min(wait, 60))
                delay *= 2
                continue
            resp.raise_for_status()
        raise RuntimeError(f"GET {url} 重试耗尽")

    def fetch_stars(self, full_names: list[str], workers: int = 8) -> dict:
        """并发拉取一批仓库的当前 star 数与头像。

        返回 {full_name: {"stars": int, "avatar": url}}；拉取失败的仓库值为 None，
        由调用方沿用旧值，不中断主流程。配额耗尽时熔断，剩余仓库直接记 None。
        """
        result: dict = {}
        stop = threading.Event()

        def one(name: str):
            if stop.is_set():
                raise RateLimitError("已熔断")
            data = self.get(f"/repos/{name}")
            return name, {
                "stars": data["stargazers_count"],
                "avatar": (data.get("owner") or {}).get("avatar_url", ""),
            }

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(one, n): n for n in full_names}
            for fut in futures:
                try:
                    name, info = fut.result()
                    result[name] = info
                except RateLimitError:
                    stop.set()
                    result[futures[fut]] = None
                except Exception:
                    result[futures[fut]] = None
        return result
