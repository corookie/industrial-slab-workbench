import io
import json
import zipfile

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis import run_analysis
from app.data import Store, quality_frame, synthetic_dataframe, write_json
from app.privacy import (
    NOTICE,
    POLICY,
    PUBLIC_NOTICE,
    create_independent_public_dataframe,
    create_public_dataframe,
    ensure_public_dataset,
    save_independent_public_release,
    save_release,
    top_grade_names,
    write_independent_public_demo,
)
from app.schema import AnalysisSpec, Filters, Query


def private_source():
    d = synthetic_dataframe(1500)
    d['steel_grade'] = ['SECRET-A']*700 + ['SECRET-B']*300 + ['SECRET-C']*200 + ['SECRET-D']*150 + ['SECRET-E']*100 + ['SECRET-F']*50
    d['source_file'] = 'confidential-production.xlsx'
    d['source_sheet'] = 'confidential-sheet'
    d['furnace'] = 'PRIVATE-FURNACE'
    return quality_frame(d)


def test_top_five_fixed_before_filter_and_anonymous_generation():
    raw = private_source()
    before = raw.copy(deep=True)
    assert top_grade_names(raw) == [f'SECRET-{c}' for c in 'ABCDE']
    demo, mapping = create_public_dataframe(raw, seed=321, per_grade=100)
    again, _ = create_public_dataframe(raw, seed=321, per_grade=100)
    pd.testing.assert_frame_equal(demo, again)
    pd.testing.assert_frame_equal(raw, before)
    assert {m['source_grade'] for m in mapping} == set(top_grade_names(raw))
    assert demo.steel_grade.value_counts().to_dict() == {f'G{i:02d}': 100 for i in range(1,6)}
    assert len(demo) == 500 and demo.slab_id.nunique() == 500
    text = demo.to_csv(index=False)
    for secret in ['SECRET-', 'PRIVATE-FURNACE', 'confidential-', '2023-02', 'DEMO-']:
        assert secret not in text
    assert demo.produced_at.str.startswith('2025-01').all()
    assert demo.furnace.isna().all() and not demo.invalid.any()
    # No entire confidential numeric record is copied into the demo.
    numeric = ['length','width','thickness','rough_thickness','exit_temp','temp_drop','process_time']
    assert demo[numeric].merge(raw[numeric], on=numeric).empty


def test_top_five_missing_and_tie_policies():
    d = private_source()
    d['steel_grade'] = [c for c in ['Z','Y','X','W','V','U'] for _ in range(250)]
    assert top_grade_names(d) == ['U','V','W','X','Y']
    d['steel_grade'] = 'ONLY'
    with pytest.raises(ValueError, match='至少'):
        create_public_dataframe(d)


def test_public_loader_accepts_only_independent_release_files(tmp_path):
    project = tmp_path / 'project'
    demo_path = project / 'data' / 'examples' / 'public_demo.csv'
    write_independent_public_demo(demo_path)
    store = Store(tmp_path / 'runtime-public')
    release = ensure_public_dataset(store, project)
    assert release['source_kind'] == 'simulated'
    assert release['release']['data_origin'] == 'independent_simulation'
    assert release['rows'] == 10000

    modified = pd.read_csv(demo_path)
    modified.loc[0, 'temp_drop'] = modified.loc[0, 'temp_drop'] + 1
    modified.to_csv(demo_path, index=False, encoding='utf-8-sig')
    with pytest.raises(ValueError, match='内容校验失败'):
        ensure_public_dataset(Store(tmp_path / 'runtime-modified'), project)

    derived, _ = create_public_dataframe(private_source(), per_grade=2000)
    derived.to_csv(demo_path, index=False, encoding='utf-8-sig')
    write_json(demo_path.with_suffix('.json'), POLICY)
    with pytest.raises(ValueError, match='不是完全独立模拟'):
        ensure_public_dataset(Store(tmp_path / 'runtime-derived'), project)


def test_public_api_blocks_private_data_and_raw_uploads(tmp_path, monkeypatch):
    store = Store(tmp_path)
    raw = store.save_dataset(private_source(), 'secret production dataset', 'real')
    # A local source-derived draft can exist in the Store, but public mode must
    # expose only the independent simulation release.
    derived, _ = create_public_dataframe(private_source(), per_grade=100)
    derived_release = save_release(store, derived)
    demo = create_independent_public_dataframe(per_grade=100)
    release = save_independent_public_release(store, demo)
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setattr(main, 'PUBLIC_MODE', True)
    client = TestClient(main.app)
    assert client.get('/api/health').json()['mode'] == 'public_demo'
    assert client.get('/api/health').json()['public_data'] == 'independent_simulation'
    assert [d['id'] for d in client.get('/api/datasets').json()] == [release['id']]
    assert client.get(f'/api/datasets/{derived_release["id"]}').status_code == 404
    assert client.post('/api/uploads', files={'files':('raw.csv',b'steel_grade\nSECRET-A\n','text/csv')}).status_code == 403
    assert client.post('/api/datasets/import', json={'name':'secret','source_kind':'real','units_confirmed':True,'tables':[{'upload_id':raw['id'],'sheet':'CSV'}]}).status_code == 403
    for method, suffix, payload in [('get','',None),('post','/query',{}),('post','/export',{}),('post','/records/any',{}),('post','/analyses',AnalysisSpec(steel_grade='SECRET-A',controls={'exit_temp':[1100,1300]},bins=[20,40,100]).model_dump())]:
        response = getattr(client, method)(f'/api/datasets/{raw["id"]}{suffix}', **({'json':payload} if payload is not None else {}))
        assert response.status_code == 404
        assert 'SECRET' not in response.text
    fake_id = 'a'*32
    folder = store.root/'analyses'/fake_id
    folder.mkdir()
    write_json(folder/'result.json', {'id':fake_id,'dataset_id':raw['id'],'source_kind':'real'})
    (folder/'samples.csv').write_text('CONFIDENTIAL')
    assert client.get(f'/api/analyses/{fake_id}/artifacts/samples.csv').status_code == 404
    assert client.post(f'/api/analyses/{fake_id}/rerun').status_code == 404
    assert not client.get('/api/analyses').json()
    query = client.post(f'/api/datasets/{release["id"]}/query', json={}).json()
    assert query['total'] == sum(g['value'] for g in query['grades']) == 500
    assert {g['name'] for g in query['grades']} == {f'G{i:02d}' for i in range(1,6)}
    exported = client.post(f'/api/datasets/{release["id"]}/export', json={})
    frame = pd.read_csv(io.BytesIO(exported.content))
    assert len(frame) == 500 and frame.data_status.str.contains('完全独立模拟').all()
    assert 'SECRET' not in exported.text


def test_public_report_and_zip_use_only_synthetic_scope(tmp_path):
    store = Store(tmp_path)
    demo = create_independent_public_dataframe(per_grade=100)
    meta = save_independent_public_release(store, demo)
    spec = AnalysisSpec(steel_grade='G01', controls={'exit_temp':[900,1400]}, bins=[20,38,42,100])
    result = run_analysis(store, meta['id'], spec)
    assert result['source_kind'] == 'simulated' and PUBLIC_NOTICE in result['warnings']
    assert sum(g['n'] for g in result['groups']) == result['counts']['analyzed'] == 100
    folder = store.root/'analyses'/result['id']
    with zipfile.ZipFile(folder/'bundle.zip') as bundle:
        for name in ['report.md','report.html','samples.csv','result.json','parameters.json','figure.svg']:
            text = bundle.read(name).decode('utf-8-sig')
            for secret in ['SECRET-', 'PRIVATE-FURNACE', 'confidential-production', '2023-02', 'DEMO-']:
                assert secret not in text
        assert '完全独立模拟' in bundle.read('report.html').decode()
    samples = pd.read_csv(folder/'samples.csv')
    assert samples.steel_grade.unique().tolist() == ['G01']
    assert not result['provenance']
