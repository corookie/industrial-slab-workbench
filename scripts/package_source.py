"""Package only reviewed, tracked repository files.

This deliberately excludes private runtime data and local screenshots.
"""

import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
names = [Path(item.decode()) for item in result.stdout.split(b'\0') if item]
if not names:
    raise SystemExit('先审核并提交安全的仓库文件，再生成源码包')
blocked_parts = {'runtime', 'runtime-public', 'deliverables', 'private-review', '.venv', 'node_modules'}
blocked_names = {'.env', 'public_demo_source.csv'}
for name in names:
    if blocked_parts.intersection(name.parts) or name.name in blocked_names:
        raise SystemExit(f'仓库含不应分发的文件：{name}')

out = ROOT / 'deliverables' / 'industrial-slab-workbench-source.zip'
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        path = ROOT / name
        if path.is_file():
            archive.write(path, 'industrial-slab-workbench/' + name.as_posix())
print('Source package:', out, out.stat().st_size, 'bytes')
