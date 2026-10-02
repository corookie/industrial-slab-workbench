"""Import a local file through the same preview/mapping pipeline as the web UI."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.data import Store
store = Store(ROOT / 'runtime')
from app.schema import ImportSpec, TableSpec

parser = argparse.ArgumentParser()
parser.add_argument('file', type=Path)
parser.add_argument('--name', default=None)
parser.add_argument('--confirm-units', action='store_true', help='Confirm inferred mappings and canonical units before importing')
args = parser.parse_args()
uploaded = store.save_upload(args.file.name, args.file.read_bytes())
for t in uploaded['tables']:
    print(t['sheet'], t['rows'], t['mapping'], t['units'])
if not args.confirm_units:
    print('Preview only. Review above; use the UI for unit changes or add --confirm-units when correct.')
    sys.exit(0)
table = uploaded['tables'][0]
result = store.import_data(ImportSpec(name=args.name or args.file.stem, source_kind='real', units_confirmed=True,
    tables=[TableSpec(upload_id=uploaded['id'], sheet=table['sheet'], mapping=table['mapping'], units=table['units'])]))
print('Imported:', result['id'], result['rows'], 'anomaly rows:', result['quality']['invalid_rows'])
