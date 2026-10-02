"""Build the public Vue app into GitHub Pages' main/docs directory.

Only generated site files are replaced. Local notes and screenshots in docs/
are left untouched and excluded from Git by .gitignore.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SITE = ROOT / "docs"


def https_origin(value: str) -> str:
    parsed = urlparse(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise argparse.ArgumentTypeError("--api-base 须为不含路径或凭据的 HTTPS 域名")
    return value.rstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, type=https_origin)
    parser.add_argument("--base-path", default="/industrial-slab-workbench/")
    args = parser.parse_args()
    if not args.base_path.startswith("/") or not args.base_path.endswith("/") or ".." in args.base_path:
        parser.error("--base-path 须以 / 开头和结尾，且不能包含 ..")

    env = os.environ.copy()
    env["VITE_API_BASE"] = args.api_base
    env["VITE_BASE_PATH"] = args.base_path
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND, env=env, check=True)

    built = FRONTEND / "dist"
    SITE.mkdir(exist_ok=True)
    assets = SITE / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(built / "assets", assets)
    shutil.copy2(built / "index.html", SITE / "index.html")
    favicon = built / "favicon.svg"
    if favicon.exists():
        shutil.copy2(favicon, SITE / "favicon.svg")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Pages ready: {SITE / 'index.html'} | API: {args.api_base}")


if __name__ == "__main__":
    main()
