"""Run an end-to-end check against the public demonstration service."""
import argparse
import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='https://industrial-slab-workbench-api.onrender.com')
parser.add_argument('--output', default='runtime/online-verification')
args = parser.parse_args()
origin = args.url.rstrip('/')
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)


def request(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(origin + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def api(path, payload=None):
    return json.loads(request(path, payload))


datasets = api('/api/datasets')
assert len(datasets) == 1
dataset = datasets[0]['id']
filters = {'grades': ['G01'], 'exclude_invalid': True}
query = api(f'/api/datasets/{dataset}/query', {'filters': filters, 'page': 2})
assert query['total'] == 2000 and query['page'] == 2
assert sum(g['value'] for g in query['grades']) == query['total']
assert all(row['steel_grade'] == 'G01' for row in query['records'])
selected = query['records'][0]
record = api(f'/api/datasets/{dataset}/records/{selected["record_id"]}', filters)
assert record == selected
result = api(f'/api/datasets/{dataset}/analyses', {
    'filters': filters, 'steel_grade': 'G01', 'variable': 'rough_thickness',
    'bins': [20, 30, 40, 55], 'controls': {'exit_temp': [1180, 1220], 'process_time': [190, 230]},
    'relationship_fields': ['rough_thickness', 'process_time', 'exit_temp', 'furnace_time', 'width'],
    'effect_step': 1, 'error_bar': 'sd',
})
assert result['scope_sha256'] == query['scope']
assert result['counts']['current_scope'] == query['total']
assert sum(group['n'] for group in result['groups']) == result['counts']['analyzed']
assert result['release']['data_origin'] == 'independent_simulation'
for name in ['figure.png', 'figure.pdf', 'relationships.csv', 'statistics.csv', 'report.html', 'bundle.zip']:
    content = request(result['artifacts'][name])
    assert len(content) > 100
    (output / name).write_bytes(content)
samples = list(csv.DictReader(io.StringIO(request(result['artifacts']['samples.csv']).decode('utf-8-sig'))))
assert len(samples) == result['counts']['analyzed']
assert all(row['steel_grade'] == 'G01' and 1180 <= float(row['exit_temp']) <= 1220
           and 190 <= float(row['process_time']) <= 230 for row in samples)
with zipfile.ZipFile(output / 'bundle.zip') as bundle:
    assert bundle.testzip() is None
    assert {'figure.png', 'report.html', 'result.json', 'samples.csv'}.issubset(bundle.namelist())
conditions = api(f'/api/analyses/{result["id"]}/conditions')
assert conditions['points']
rerun = api(f'/api/analyses/{result["id"]}/rerun', {})
assert rerun['samples_sha256'] == result['samples_sha256']
assert rerun['groups'] == result['groups']
(output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({'online_check': 'passed', 'scope': query['total'],
                  'analyzed': result['counts']['analyzed'], 'analysis_id': result['id'],
                  'downloaded_to': str(output.resolve()), 'rerun_identical': True}, ensure_ascii=False))
