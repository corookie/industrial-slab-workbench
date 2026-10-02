import pandas as pd
from fastapi.testclient import TestClient

from app import main
from app.data import Store, synthetic_dataframe
from app.subsets import create_original_top_five, hide_dataset


def test_original_top_five_preserves_records_and_quality(tmp_path):
    store = Store(tmp_path)
    d = synthetic_dataframe(100)
    d['steel_grade'] = ['A']*40+['B']*20+['C']*15+['D']*10+['E']*9+['F']*6
    # Rank on all source rows, not after removing anomalies.
    d.loc[d.steel_grade=='E','temp_drop'] = -10
    source = store.save_dataset(d, 'original', 'real')
    raw, _ = store.get(source['id'])
    before = raw.copy(deep=True)
    subset = create_original_top_five(store, source['id'])
    selected, _ = store.get(subset['id'])
    assert subset['selection']['grades'] == list('ABCDE')
    assert len(selected)==94 and subset['source_kind']=='real'
    assert 'F' not in selected.steel_grade.values
    expected = raw[raw.steel_grade.isin(list('ABCDE'))].reset_index(drop=True)
    pd.testing.assert_frame_equal(selected.drop(columns=['record_id','source_record_id']), expected.drop(columns=['record_id']))
    assert selected.source_record_id.tolist()==expected.record_id.tolist()
    pd.testing.assert_frame_equal(before, raw)
    assert create_original_top_five(store, source['id'])['id']==subset['id']


def test_private_dropdown_exposes_only_subset_and_public_mode_blocks_it(tmp_path, monkeypatch):
    store = Store(tmp_path)
    d = synthetic_dataframe(100)
    d['steel_grade'] = ['A']*40+['B']*20+['C']*15+['D']*10+['E']*9+['F']*6
    source = store.save_dataset(d,'original','real')
    subset = create_original_top_five(store,source['id'])
    hide_dataset(store,source['id'])
    monkeypatch.setattr(main,'store',store)
    monkeypatch.setattr(main,'PUBLIC_MODE',False)
    client=TestClient(main.app)
    assert [m['id'] for m in client.get('/api/datasets').json()]==[subset['id']]
    assert client.get('/api/datasets/'+source['id']).status_code==404
    q=client.post('/api/datasets/'+subset['id']+'/query',json={}).json()
    assert len(q['grades'])==5 and q['total']==92
    assert sum(g['value'] for g in q['grades'])==q['total']
    exported=client.post('/api/datasets/'+subset['id']+'/export',json={})
    assert exported.status_code==200 and 'DEMO-' in exported.text
    monkeypatch.setattr(main,'PUBLIC_MODE',True)
    assert client.get('/api/datasets/'+subset['id']).status_code==404
    assert client.post('/api/datasets/'+subset['id']+'/export',json={}).status_code==404
