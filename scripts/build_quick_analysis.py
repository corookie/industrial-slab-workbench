"""Precompute one real Python experiment from the exact bundled demo rows.

Run with the project's Python environment. No server, uploads or private data
are read. The static results are immutable; edited filters cannot recalculate
this saved experiment in the browser.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.analysis import run_analysis
from app.conditions import build_conditions
from app.data import write_json
from app.schema import AnalysisSpec
import pandas as pd
from build_quick_demo import build_payload, write_bundle

OUTPUT = ROOT / 'frontend/src/data/quick-analysis.json'
ASSETS = ROOT / 'frontend/public/quick-analysis'

# Ranges fixed before inspecting fitted effects; enough samples in each group.
DEFAULT_PARAMETERS = {
    'filters': {'grades': [], 'ranges': {}, 'date_start': None, 'date_end': None, 'exclude_invalid': True},
    'steel_grade': 'G01', 'variable': 'rough_thickness',
    'controls': {'exit_temp': [1170, 1230], 'process_time': [140, 220]},
    'bins': [24, 32, 36, 44], 'error_bar': 'sd', 'effect_step': 1,
    'relationship_fields': ['rough_thickness', 'process_time', 'exit_temp', 'furnace_time', 'width'],
}


class BundledStore:
    """Minimal, isolated input for the same analysis used by the API."""
    def __init__(self, root: Path, bundle: dict):
        self.root = root
        self.frame = pd.DataFrame(bundle['rows'], columns=bundle['columns'])
        self.frame['record_id'] = self.frame.backend_row_index.map(lambda index: f'quick-{index}')
        # Keep UI identity, but do not expose the full-demo CSV ordinal as data.
        self.frame = self.frame.drop(columns=['backend_row_index'])
        folder = root / 'datasets' / bundle['meta']['id']
        folder.mkdir(parents=True)
        self.frame.to_csv(folder / 'normalized.csv', index=False, encoding='utf-8-sig')
        self.meta = {**bundle['meta'], 'sha256': hashlib.sha256((folder / 'normalized.csv').read_bytes()).hexdigest()}
        (root / 'analyses').mkdir()

    def get(self, ident):
        if ident != self.meta['id']:
            raise ValueError('内置数据集标识不一致')
        return self.frame, self.meta


def main():
    write_bundle()
    bundle = build_payload()
    with tempfile.TemporaryDirectory(prefix='slab-quick-analysis-') as temporary:
        store = BundledStore(Path(temporary), bundle)
        result = run_analysis(store, bundle['meta']['id'], AnalysisSpec(**DEFAULT_PARAMETERS))
        folder = store.root / 'analyses' / result['id']
        conditions = build_conditions(folder, result)
        assert result['counts']['source'] == result['counts']['current_scope'] == 1000
        assert sum(group['n'] for group in result['groups']) == result['counts']['analyzed']
        assert result['relationships']['n'] == result['counts']['analyzed']
        assert result['source_kind'] == 'simulated'
        result['precomputed'] = True
        result['quick_dataset_sha256'] = bundle['meta']['sha256']
        result['artifacts'] = {name: f'quick-analysis/{name}' for name in result['artifacts']}
        write_json(folder / 'result.json', result)
        write_json(folder / 'conditions.json', conditions)
        # The complete 1,000-row input enables exact reproduction of the scope.
        shutil.copyfile(store.root / 'datasets' / bundle['meta']['id'] / 'normalized.csv', folder / 'dataset.csv')
        with zipfile.ZipFile(folder / 'bundle.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(folder.iterdir()):
                if item.name != 'bundle.zip':
                    archive.write(item, item.name)
        hashes = {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in sorted(folder.iterdir())}
        payload = {'version': 'quick-analysis-v1', 'result': result, 'conditions': conditions, 'files_sha256': hashes}
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
        ASSETS.mkdir(parents=True, exist_ok=True)
        for item in folder.iterdir():
            shutil.copyfile(item, ASSETS / item.name)
        print(json.dumps({'dataset_rows': 1000, 'analysis_rows': result['counts']['analyzed'],
                          'groups': [group['n'] for group in result['groups']],
                          'conclusion': result['relationships']['explanation']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
