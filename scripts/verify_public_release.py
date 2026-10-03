"""Check that the GitHub/Render release contains independent simulation only.

Run after `git add` and before `git push`. It prints no confidential names.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.privacy import PUBLIC_DEMO_SEED, PUBLIC_POLICY, write_independent_public_demo


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_paths() -> list[Path]:
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
    return [Path(item.decode()) for item in result.stdout.split(b'\0') if item]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', help='Optional running public service origin, for API isolation checks')
    args = parser.parse_args()
    files = tracked_paths()
    if not files:
        raise SystemExit('尚未暂存公开仓库文件，请先 git add 再审计')
    forbidden_parts = {'runtime', 'runtime-public', 'private-review', 'deliverables', '.venv', 'node_modules', 'screens'}
    forbidden_names = {'.env', 'release-mapping.json'}
    if any(forbidden_parts.intersection(path.parts) or path.name in forbidden_names for path in files):
        raise SystemExit('暂存列表含私有目录、截图或本机配置，停止发布')
    required = {Path('data/examples/public_demo.csv'), Path('data/examples/public_demo.json')}
    if not required.issubset(files):
        raise SystemExit('公开独立模拟数据和策略文件必须同时暂存')

    public_csv = ROOT / 'data/examples/public_demo.csv'
    public_policy = json.loads((ROOT / 'data/examples/public_demo.json').read_text(encoding='utf-8-sig'))
    if (public_policy.get('version') != PUBLIC_POLICY['version']
            or public_policy.get('data_origin') != 'independent_simulation'
            or public_policy.get('seed') != PUBLIC_DEMO_SEED):
        raise SystemExit('公开数据策略不是固定参数的独立模拟版本')
    with tempfile.TemporaryDirectory() as folder:
        regenerated = Path(folder) / 'demo.csv'
        write_independent_public_demo(regenerated, seed=public_policy['seed'], per_grade=public_policy['records_per_grade'])
        if digest(public_csv) != digest(regenerated):
            raise SystemExit('公开 CSV 与独立模拟生成器不一致，停止发布')
    frame = pd.read_csv(public_csv, usecols=['slab_id', 'steel_grade', 'data_status', 'source_file'])
    if (len(frame) != 10000 or frame.steel_grade.value_counts().to_dict() != {f'G{i:02d}': 2000 for i in range(1, 6)}
            or not frame.slab_id.str.startswith('SIM-').all()
            or not frame.data_status.eq('完全独立模拟示例；非真实生产记录').all()
            or not frame.source_file.eq('独立模拟示例.csv').all()):
        raise SystemExit('公开 CSV 的数量、类别或来源标记无效')

    # If the original confidential data exists on this machine, also check
    # every tracked text file for known direct identifiers without logging them.
    mapping = ROOT / 'runtime/private-review/release-mapping.json'
    checked_private = False
    if mapping.exists():
        review = json.loads(mapping.read_text(encoding='utf-8'))
        tokens = {str(item.get('source_grade', '')) for item in review.get('mapping', [])}
        tokens = {token for token in tokens if len(token) >= 4}
        for path in files:
            if path.suffix not in {'.md', '.py', '.js', '.vue', '.json', '.csv', '.html', '.css', '.yaml', '.yml', '.svg', '.txt'}:
                continue
            content = (ROOT / path).read_text(encoding='utf-8-sig', errors='replace')
            for token in tokens:
                if re.search(r'(?<![A-Za-z0-9])' + re.escape(token) + r'(?![A-Za-z0-9])', content):
                    raise SystemExit('暂存文件含真实钢种标识，停止发布')
        checked_private = True

    if args.url:
        import urllib.error
        import urllib.request
        origin = args.url.rstrip('/')
        health = json.load(urllib.request.urlopen(origin + '/api/health', timeout=120))
        if health.get('mode') != 'public_demo' or health.get('public_data') != 'independent_simulation':
            raise SystemExit('线上服务未运行独立模拟公开模式')
        datasets = json.load(urllib.request.urlopen(origin + '/api/datasets', timeout=120))
        if len(datasets) != 1 or datasets[0].get('release', {}).get('data_origin') != 'independent_simulation':
            raise SystemExit('线上数据集不符合公开模式要求')
        try:
            boundary = 'slab-release-audit'
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="audit.csv"\r\n'
                    f'Content-Type: text/csv\r\n\r\nslab_id,steel_grade\r\nSIM-AUDIT,G01\r\n--{boundary}--\r\n').encode()
            urllib.request.urlopen(urllib.request.Request(origin + '/api/uploads', data=body, method='POST',
                                   headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}), timeout=120)
            raise SystemExit('线上公开服务允许上传，停止发布')
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise SystemExit('线上上传隔离状态异常') from error

    print(json.dumps({'release': PUBLIC_POLICY['version'], 'rows': len(frame), 'grades': 5,
                      'tracked_files': len(files), 'private_identifier_scan': checked_private,
                      'remote_checked': bool(args.url)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
