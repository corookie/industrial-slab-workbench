import hashlib
import uuid

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app import main
from app.analysis import run_analysis
from app.data import Store, synthetic_dataframe, write_json
from app.schema import AnalysisSpec


def save_snapshot(store, frame, source_kind='simulated'):
    """Create a minimal, hash-checked analysis snapshot from synthetic rows."""
    dataset = store.save_dataset(synthetic_dataframe(12), 'synthetic fixture', source_kind)
    analysis_id = uuid.uuid4().hex
    folder = store.root / 'analyses' / analysis_id
    folder.mkdir()
    samples = folder / 'samples.csv'
    frame.to_csv(samples, index=False, encoding='utf-8-sig')
    result = {
        'id': analysis_id,
        'dataset_id': dataset['id'],
        'source_kind': source_kind,
        'samples_sha256': hashlib.sha256(samples.read_bytes()).hexdigest(),
        'counts': {'analyzed': len(frame)},
        'conditions': ['钢种：SYNTHETIC', '控制条件 出炉温度：1100—1300 °C'],
    }
    write_json(folder / 'result.json', result)
    return dataset, analysis_id, folder, result


def client_for(store, monkeypatch, public=False):
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setattr(main, 'PUBLIC_MODE', public)
    return TestClient(main.app)


def test_conditions_reads_the_actual_saved_analysis_snapshot(tmp_path, monkeypatch):
    store = Store(tmp_path)
    dataset = store.save_dataset(synthetic_dataframe(120), 'synthetic analysis fixture', 'simulated')
    result = run_analysis(
        store,
        dataset['id'],
        AnalysisSpec(steel_grade='DEMO-A', controls={'exit_temp': [1100, 1300]}, bins=[20, 38, 42, 100]),
    )

    response = client_for(store, monkeypatch).get(f'/api/analyses/{result["id"]}/conditions')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['analysis_id'] == result['id']
    assert payload['dataset_id'] == dataset['id']
    assert payload['samples_sha256'] == result['samples_sha256']
    assert payload['counts']['analyzed'] == result['counts']['analyzed']
    assert payload['counts']['eligible'] + payload['counts']['missing_coordinates'] == result['counts']['analyzed']
    assert payload['points']
    assert 'source_file' not in response.text


def test_conditions_bounded_sampling_uses_full_valid_snapshot_ranges(tmp_path, monkeypatch):
    store = Store(tmp_path)
    valid = 5001
    frame = pd.DataFrame({
        'record_id': [f'r{i:05d}' for i in range(valid)],
        'slab_id': [f's{i:05d}' for i in range(valid)],
        'source_row': np.arange(2, valid + 2),
        'steel_grade': 'SYNTHETIC',
        'exit_temp': np.full(valid, 1200.0),
        'process_time': np.full(valid, 210.0),
        'rough_thickness': np.full(valid, 40.0),
        'temp_drop': np.full(valid, 100.0),
        'group_index': 1,
        'produced_at': '2026-01-01T00:00:00',
        'source_file': 'private-source.xlsx',
    })
    frame.loc[0, 'slab_id'] = '000123'
    frame.loc[1, 'slab_id'] = 'NA'
    frame.loc[2, 'slab_id'] = None
    # This is a valid row that deterministic 5,001 -> 5,000 sampling skips.
    frame.loc[4999, ['exit_temp', 'temp_drop']] = [9999.0, -100.0]
    # The last valid row proves the equal-interval sampler retains the tail.
    frame.loc[5000, ['rough_thickness', 'temp_drop']] = [41.0, 101.0]
    invalid = pd.DataFrame([
        {'record_id': 'missing', 'exit_temp': 1200, 'process_time': None, 'rough_thickness': 40, 'temp_drop': 100},
        {'record_id': 'infinite-axis', 'exit_temp': np.inf, 'process_time': 210, 'rough_thickness': 40, 'temp_drop': 100},
        {'record_id': 'infinite-color', 'exit_temp': 1200, 'process_time': 210, 'rough_thickness': 40, 'temp_drop': -np.inf},
    ])
    dataset, analysis_id, _, result = save_snapshot(store, pd.concat([frame, invalid], ignore_index=True))

    response = client_for(store, monkeypatch).get(f'/api/analyses/{analysis_id}/conditions')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['analysis_id'] == analysis_id
    assert payload['dataset_id'] == dataset['id']
    assert payload['samples_sha256'] == result['samples_sha256']
    assert payload['counts'] == {'analyzed': 5004, 'eligible': 5001, 'missing_coordinates': 3, 'rendered': 5000}
    assert payload['sampling'] == 'deterministic_record_order'
    assert payload['points'][0]['record_id'] == 'r00000'
    assert payload['points'][0]['slab_id'] == '000123'
    assert payload['points'][1]['slab_id'] == 'NA'
    assert payload['points'][2]['slab_id'] is None
    assert payload['points'][-1]['record_id'] == 'r05000'
    assert 'r04999' not in {point['record_id'] for point in payload['points']}
    assert payload['bounds']['exit_temp'] == {'min': 1200.0, 'max': 9999.0}
    assert payload['bounds']['process_time'] == {'min': 210.0, 'max': 210.0}
    assert payload['bounds']['rough_thickness'] == {'min': 40.0, 'max': 41.0}
    assert payload['color_scale'] == {'min': -100.0, 'max': 101.0}
    assert set(payload['points'][0]) == {
        'record_id', 'slab_id', 'source_row', 'steel_grade', 'exit_temp', 'process_time',
        'rough_thickness', 'temp_drop', 'group_index', 'produced_at',
    }
    assert 'source_file' not in response.text and 'private-source.xlsx' not in response.text


def test_conditions_missing_fields_and_all_nonfinite_values_are_explicit(tmp_path, monkeypatch):
    store = Store(tmp_path)
    missing_frame = pd.DataFrame([{'record_id': 'legacy-1', 'exit_temp': 1200, 'temp_drop': 100}])
    _, missing_id, _, _ = save_snapshot(store, missing_frame)
    client = client_for(store, monkeypatch)
    missing = client.get(f'/api/analyses/{missing_id}/conditions')
    assert missing.status_code == 200
    missing_payload = missing.json()
    assert missing_payload['points'] == []
    assert missing_payload['counts'] == {'analyzed': 1, 'eligible': 0, 'missing_coordinates': 1, 'rendered': 0}
    assert missing_payload['bounds'] == {
        'exit_temp': {'min': None, 'max': None},
        'process_time': {'min': None, 'max': None},
        'rough_thickness': {'min': None, 'max': None},
    }
    assert missing_payload['color_scale'] == {'min': None, 'max': None}
    assert missing_payload['sampling'] == 'none'
    assert missing_payload['warnings']

    nonfinite_frame = pd.DataFrame([
        {'record_id': 'nan', 'exit_temp': np.nan, 'process_time': 210, 'rough_thickness': 40, 'temp_drop': 100},
        {'record_id': 'inf', 'exit_temp': 1200, 'process_time': np.inf, 'rough_thickness': 40, 'temp_drop': 100},
    ])
    _, nonfinite_id, _, _ = save_snapshot(store, nonfinite_frame)
    nonfinite = client.get(f'/api/analyses/{nonfinite_id}/conditions')
    assert nonfinite.status_code == 200
    nonfinite_payload = nonfinite.json()
    assert nonfinite_payload['points'] == []
    assert nonfinite_payload['counts'] == {'analyzed': 2, 'eligible': 0, 'missing_coordinates': 2, 'rendered': 0}
    assert nonfinite_payload['bounds']['exit_temp'] == {'min': None, 'max': None}
    assert nonfinite_payload['warnings']


def test_conditions_rejects_legacy_or_corrupt_snapshot_metadata(tmp_path, monkeypatch):
    store = Store(tmp_path)
    frame = pd.DataFrame([{
        'record_id': 'r1', 'exit_temp': 1200, 'process_time': 210,
        'rough_thickness': 40, 'temp_drop': 100,
    }])
    _, analysis_id, folder, result = save_snapshot(store, frame)
    client = client_for(store, monkeypatch)

    # A byte-level change must be detected before any coordinates are returned.
    (folder / 'samples.csv').write_text('private-source.xlsx', encoding='utf-8')
    corrupted = client.get(f'/api/analyses/{analysis_id}/conditions')
    assert corrupted.status_code == 409
    assert 'private-source.xlsx' not in corrupted.text

    # An older report without its snapshot fingerprint gets a controlled response.
    result.pop('samples_sha256')
    write_json(folder / 'result.json', result)
    legacy = client.get(f'/api/analyses/{analysis_id}/conditions')
    assert legacy.status_code == 409

    # Restore a valid fingerprint but reject a saved count that no longer agrees
    # with the immutable CSV.
    samples = folder / 'samples.csv'
    samples.write_bytes(frame.to_csv(index=False, encoding='utf-8-sig').encode('utf-8'))
    result['samples_sha256'] = hashlib.sha256(samples.read_bytes()).hexdigest()
    result['counts']['analyzed'] = 2
    write_json(folder / 'result.json', result)
    bad_count = client.get(f'/api/analyses/{analysis_id}/conditions')
    assert bad_count.status_code == 409

    # The path and result metadata must identify the same saved analysis.
    result['counts']['analyzed'] = len(frame)
    result['id'] = uuid.uuid4().hex
    write_json(folder / 'result.json', result)
    mismatch = client.get(f'/api/analyses/{analysis_id}/conditions')
    assert mismatch.status_code == 409


def test_conditions_reuses_private_and_public_dataset_gate(tmp_path, monkeypatch):
    store = Store(tmp_path)
    frame = pd.DataFrame([{
        'record_id': 'r1', 'slab_id': 's1', 'source_row': 2, 'steel_grade': 'SYNTHETIC',
        'exit_temp': 1200, 'process_time': 210, 'rough_thickness': 40, 'temp_drop': 100,
        'group_index': 0, 'produced_at': '2026-01-01T00:00:00', 'source_file': 'private-source.xlsx',
    }])
    _, analysis_id, _, _ = save_snapshot(store, frame, source_kind='real')
    private_client = client_for(store, monkeypatch, public=False)
    private = private_client.get(f'/api/analyses/{analysis_id}/conditions')
    assert private.status_code == 200
    assert 'private-source.xlsx' not in private.text

    public_client = client_for(store, monkeypatch, public=True)
    hidden = public_client.get(f'/api/analyses/{analysis_id}/conditions')
    assert hidden.status_code == 404
    assert 'private-source.xlsx' not in hidden.text
