"""组装 GitHub Pages 站点 public/：site/ 静态文件 + 每日快照 + 日报 + index.json。"""

import json
import shutil
from datetime import datetime, timezone

from src import config, tracker

ROOT = config.ROOT


def build() -> None:
    pub = ROOT / "public"
    if pub.exists():
        shutil.rmtree(pub)
    (pub / "data" / "snapshots").mkdir(parents=True)
    (pub / "reports").mkdir(parents=True)

    for f in (ROOT / "site").iterdir():
        if f.is_file():
            shutil.copy2(f, pub / f.name)

    snaps = sorted((ROOT / "data" / "snapshots").glob("*.json"))
    for f in snaps:
        shutil.copy2(f, pub / "data" / "snapshots" / f.name)
    for f in (ROOT / "reports").glob("*.md"):
        shutil.copy2(f, pub / "reports" / f.name)

    state = tracker.load(ROOT / "data")
    index = {
        "dates": [f.stem for f in snaps],
        "latest": snaps[-1].stem if snaps else None,
        "tracked": sorted(state.get("repos", {})),
        "site_url": config.DEFAULTS["site_url"],
        "repo_url": config.DEFAULTS["repo_url"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    index_bytes = json.dumps(index, ensure_ascii=False, indent=2)
    (pub / "data" / "index.json").write_text(index_bytes, encoding="utf-8")
    # 仓库内也留一份，方便不部署时直接查看
    (ROOT / "data" / "index.json").write_text(index_bytes, encoding="utf-8")
    print(f"[site] public/ 组装完成：{len(snaps)} 份快照 · {len(index['tracked'])} 个跟踪仓库")


if __name__ == "__main__":
    build()
