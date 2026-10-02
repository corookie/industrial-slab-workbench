"""Create a source-derived review copy under the private runtime directory.

This output is not approved for public release. The hosted site instead uses
the independently simulated data in data/examples/public_demo.csv.
"""
import argparse
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.data import Store, write_json
from app.privacy import POLICY, create_public_dataframe, save_release

parser = argparse.ArgumentParser()
parser.add_argument('--source-dir', type=Path, default=ROOT / 'runtime')
parser.add_argument('--dataset-id')
parser.add_argument('--output-dir', type=Path, default=ROOT / 'runtime' / 'private-review' / 'source-derived-store')
args = parser.parse_args()
private_root = args.source_dir.resolve()
output_root = args.output_dir.resolve()
if not output_root.is_relative_to(private_root) or output_root == private_root:
    raise SystemExit('源统计派生副本只可写入源数据目录下的私有子目录')
source = Store(args.source_dir)
meta = next((m for m in source.list_datasets() if m['id'] == args.dataset_id), None) if args.dataset_id else next((m for m in source.list_datasets() if m['source_kind'] == 'real' and not m.get('selection')), None)
if not meta:
    raise SystemExit('未找到真实源数据，请先在本地分析模式导入')
d, _ = source.get(meta['id'])
private = args.source_dir / 'private-review'
private.mkdir(exist_ok=True)
saved = private / 'release-mapping.json'
prior = json.loads(saved.read_text()) if saved.exists() else {}
seed = prior.get('seed') if prior.get('source_dataset_id') == meta['id'] else None
seed = seed if seed is not None else secrets.randbits(128)
demo, mapping = create_public_dataframe(d, seed=seed)
write_json(private / 'release-mapping.json', {'source_dataset_id': meta['id'], 'seed': seed, 'mapping': mapping, 'policy': POLICY})
release = save_release(Store(output_root), demo)
export = private / 'source-derived-demo.csv'
demo.to_csv(export, index=False, encoding='utf-8-sig')
write_json(export.with_suffix('.json'), POLICY)
print(json.dumps({'dataset_id': release['id'], 'rows': release['rows'], 'grades': [g['name'] for g in release['grades']], 'private_output': str(export), 'public_release_approved': False}, ensure_ascii=False))
