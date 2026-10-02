"""Prepare a five-grade original-data subset in the private directory only."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.data import Store
from app.subsets import create_original_top_five, hide_dataset

parser = argparse.ArgumentParser()
parser.add_argument('--dataset-id')
parser.add_argument('--data-dir', type=Path, default=ROOT/'runtime')
args = parser.parse_args()
if args.data_dir.resolve() == (ROOT/'runtime-public').resolve():
    raise SystemExit('原始记录不能放入公开演示目录')
store = Store(args.data_dir)
source = next((m for m in store.list_datasets() if m['source_kind']=='real' and not m.get('selection') and (not args.dataset_id or m['id']==args.dataset_id)), None)
if not source:
    raise SystemExit('未找到完整真实源数据')
subset = create_original_top_five(store, source['id'])
hide_dataset(store, source['id'])
print({'dataset_id':subset['id'],'rows':subset['rows'],'grades':len(subset['grades']),'invalid_rows':subset['quality']['invalid_rows']})
