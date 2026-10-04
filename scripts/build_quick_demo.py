"""Bundle a deterministic 1,000-row subset of the independent public demo.

Uses only the checked-in public simulation and field definitions. It never
reads runtime data, uploaded files, or private review copies.
"""
import ast
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'frontend/src/data/quick-demo.json'


def build_payload():
    source = ROOT / 'data/examples/public_demo.csv'
    policy = json.loads(source.with_suffix('.json').read_text(encoding='utf-8'))
    source_sha = hashlib.sha256(source.read_bytes().removeprefix(b'\xef\xbb\xbf')).hexdigest()
    if policy.get('data_origin') != 'independent_simulation' or policy.get('csv_sha256') != source_sha:
        raise ValueError('快速示例只能从已校验的独立模拟数据生成')
    tree = ast.parse((ROOT / 'backend/app/schema.py').read_text(encoding='utf-8'))
    fields = next(ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FIELDS' for t in node.targets))
    numeric = [key for key, field in fields.items() if field['kind'] == 'number']
    groups = {f'G{i:02d}': [] for i in range(1, 6)}
    with source.open(encoding='utf-8-sig', newline='') as stream:
        for index, row in enumerate(csv.DictReader(stream), 1):
            if (row['steel_grade'] not in groups or not row['slab_id'].startswith('SIM-')
                    or row['data_status'] != '完全独立模拟示例；非真实生产记录'
                    or row['source_file'] != '独立模拟示例.csv'):
                raise ValueError('独立模拟数据标识无效')
            groups[row['steel_grade']].append((index, row))
    if any(len(group) != 2000 for group in groups.values()):
        raise ValueError('独立模拟数据须为五类，每类 2,000 条')
    chosen = sorted(item for group in groups.values()
                    for item in [group[round(i * (len(group) - 1) / 199)] for i in range(200)])
    columns = [*fields, 'source_file', 'source_sheet', 'source_row', 'data_status',
               'invalid', 'quality_note', 'backend_row_index']
    records = []
    for index, raw in chosen:
        row = dict(raw, backend_row_index=index)
        for key in numeric:
            row[key] = float(row[key]) if row[key] else None
            if row[key] is not None and not math.isfinite(row[key]):
                raise ValueError('独立模拟数据含非有限数值')
        row['invalid'] = raw['invalid'].lower() == 'true'
        row['source_row'] = int(raw['source_row'])
        records.append({key: row.get(key) if row.get(key) != '' else None for key in columns})
    available = [key for key in fields if any(row[key] is not None for row in records)]
    counts = Counter(row['steel_grade'] for row in records)
    meta = {
        'id': 'quick-demo-v1', 'name': '快速独立模拟示例 · 1,000 条',
        'source_kind': 'simulated', 'frontend_only': True, 'rows': len(records),
        'available': available,
        'quality': {'invalid_rows': sum(row['invalid'] for row in records),
                    'missing': {key: sum(row[key] is None for row in records) for key in fields},
                    'duplicate_slab_ids': len(records) - len({row['slab_id'] for row in records})},
        'bounds': {key: {'min': min(row[key] for row in records if row[key] is not None),
                         'max': max(row[key] for row in records if row[key] is not None)}
                   for key in numeric if key in available},
        'grades': [{'name': name, 'count': counts[name]} for name in sorted(counts)],
        'provenance': [], 'warnings': [], 'joins': [],
        'units': {key: fields[key]['unit'] for key in available},
        'release': {**policy, 'records_per_grade': 200, 'counts': '每类 200 条，共 1,000 条；不代表真实产量或比例',
                    'subset': '每类等距选取 200 条独立模拟记录'},
        'sha256': hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }
    return {'schema': fields, 'meta': meta, 'columns': columns,
            'rows': [[row[key] for key in columns] for row in records]}


def write_bundle():
    payload = build_payload()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != content:
        OUTPUT.write_text(content, encoding='utf-8')
    print(f'Quick demo ready: {payload["meta"]["rows"]} independent simulated records')


if __name__ == '__main__':
    write_bundle()
