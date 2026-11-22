"""读取项目配置 config.json（浅层默认值 + 递归合并覆盖）。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# monitor.yml 里每日全量运行对应的 cron，二者必须一致
DAILY_CRON = "0 0 * * *"

DEFAULTS = {
    "languages": ["", "python", "typescript", "rust", "go"],
    "trending_sinces": ["daily", "weekly"],
    "radar": {"days": 7, "min_stars": 50, "top": 30},
    "surge": {"daily_threshold": 500},
    "track_retention_days": 30,
    "digest": {"trending_top": 10, "radar_top": 10, "gainers_top": 10},
    "notify": {"feishu": True, "dingtalk": True, "wecom": True},
    "site_url": "https://wlor0623.github.io/github-hot/",
    "repo_url": "https://github.com/wlor0623/github-hot",
}


def _merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # 深拷贝默认值
    path = ROOT / "config.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            _merge(cfg, json.load(f))
    return cfg
