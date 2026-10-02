import io
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.analysis import calculate_groups, run_analysis
from app.data import Store, apply_filters, synthetic_dataframe
from app.schema import AnalysisSpec, Filters, ImportSpec, Query, TableSpec

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)

@pytest.fixture
def dataset(store):
    return store.save_dataset(synthetic_dataframe(400), '测试模拟数据', 'simulated')

def test_query_reconciles_filter_charts_table_selection(store, dataset):
    filters = Filters(grades=['DEMO-A'], ranges={'rough_thickness': [35, 45], 'exit_temp': [1180, 1220]})
    raw, _ = store.get(dataset['id'])
    expected = raw[(raw.steel_grade == 'DEMO-A') & raw.rough_thickness.between(35,45) & raw.exit_temp.between(1180,1220) & ~raw.invalid]
    query = store.query(dataset['id'], Query(filters=filters, page_size=200))
    assert query['total'] == len(expected) == len(query['records'])
    assert sum(g['value'] for g in query['grades']) == len(expected)
    for key, hist in query['histograms'].items():
        assert sum(hist['counts']) == hist['valid_n'] == int(expected[key].notna().sum())
    assert {p[2] for p in query['scatter']} <= set(expected.record_id)
    picked = query['records'][-1]
    record = store.record(dataset['id'], picked['record_id'], filters)
    assert record['record_id'] == picked['record_id']
    assert record['length'] == picked['length']
    with pytest.raises(ValueError):
        store.record(dataset['id'], picked['record_id'], Filters(grades=['impossible']))

def test_empty_filter_and_invalid_ranges(store, dataset):
    q = store.query(dataset['id'], Query(filters=Filters(grades=['missing'])))
    assert q['total'] == 0 and q['selected'] is None and not q['scatter']
    with pytest.raises(ValueError):
        store.query(dataset['id'], Query(filters=Filters(ranges={'thickness':[250,200]})))

def test_group_boundaries_and_sample_sd():
    d = synthetic_dataframe(5)
    d['rough_thickness'] = [30, 38, 42, 50, 51]
    d['temp_drop'] = [100, 110, 120, 140, 160]
    work, groups, pairs = calculate_groups(d, 'rough_thickness', [30,38,42,50])
    assert [g['n'] for g in groups] == [1,1,2]
    assert groups[-1]['mean'] == 130
    assert groups[-1]['sd'] == pytest.approx(np.std([120,140],ddof=1))
    assert groups[0]['ci95_low'] is None
    assert pairs[-1]['mean_difference_b_minus_a'] == 20
    with pytest.raises(ValueError):
        calculate_groups(d, 'rough_thickness', [30,30,50])

def test_analysis_matches_saved_scope_and_reproduces(store, dataset):
    filters = Filters(ranges={'width':[1100,1450]})
    spec = AnalysisSpec(filters=filters, steel_grade='DEMO-A', controls={'exit_temp':[1180,1220], 'process_time':[180,240]}, bins=[30,38,42,50])
    result = run_analysis(store,dataset['id'],spec)
    raw,_=store.get(dataset['id'])
    expected=raw[(raw.steel_grade=='DEMO-A') & raw.width.between(1100,1450) & raw.exit_temp.between(1180,1220) & raw.process_time.between(180,240) & ~raw.invalid]
    assert result['counts']['analyzed']==len(expected)==sum(g['n'] for g in result['groups'])
    assert np.average([g['mean'] for g in result['groups']], weights=[g['n'] for g in result['groups']])==pytest.approx(expected.temp_drop.mean())
    again=run_analysis(store,dataset['id'],spec)
    assert result['groups']==again['groups']
    assert result['parameter_sha256']==again['parameter_sha256']
    assert result['samples_sha256']==again['samples_sha256']
    for file in ['figure.png','figure.pdf','figure.svg','report.html','bundle.zip']:
        assert (store.root/'analyses'/result['id']/file).stat().st_size>100

def make_upload(store, content):
    return store.save_upload('test.csv', content.encode())

def table(u, role='main', mapping=None, units=None):
    return TableSpec(upload_id=u['id'], sheet='CSV',role=role,mapping=mapping or u['tables'][0]['mapping'],units=units or u['tables'][0]['units'])

def test_import_optional_fields_units_and_id_generation(store):
    u=make_upload(store,'钢种,长度,粗轧温降\nA,10,140\nA,,145\n')
    meta=store.import_data(ImportSpec(name='optional',units_confirmed=True,tables=[table(u,units={'length':'m','temp_drop':'°C'})]))
    d,_=store.get(meta['id'])
    assert d.length.iloc[0]==10000
    assert d.record_id.nunique()==2 and d.slab_id.isna().all()
    assert meta['quality']['missing']['thickness']==2
    reloaded=Store(store.root)
    pd.testing.assert_series_equal(d.record_id,reloaded.get(meta['id'])[0].record_id)

def test_join_never_expands_and_preserves_primary(store):
    a=make_upload(store,'板坯编号,钢种,出钢温度\nS1,A,1200\nS2,B,1210\n')
    b=make_upload(store,'板坯编号,粗轧温降,出钢温度\nS1,145,1300\nS2,150,1210\n')
    meta=store.import_data(ImportSpec(name='joined',units_confirmed=True,tables=[table(a),table(b,'join')]))
    d,_=store.get(meta['id'])
    assert len(d)==2 and d.exit_temp.iloc[0]==1200 and d.temp_drop.iloc[0]==145
    assert meta['joins'][0]['conflicts']['exit_temp']==1
    dup=make_upload(store,'板坯编号,粗轧温降\nS1,145\nS1,146\n')
    with pytest.raises(ValueError,match='重复'):
        store.import_data(ImportSpec(name='bad',units_confirmed=True,tables=[table(a),table(dup,'join')]))

def test_missing_join_key_blocked_append_preserves_rows(store):
    a=make_upload(store,'钢种,粗轧温降\nA,145\nA,146\n')
    b=make_upload(store,'钢种,粗轧温降\nB,155\n')
    with pytest.raises(ValueError,match='编号'):
        store.import_data(ImportSpec(name='bad',units_confirmed=True,tables=[table(a),table(b,'join')]))
    m=store.import_data(ImportSpec(name='append',units_confirmed=True,tables=[table(a),table(b,'append')]))
    assert m['rows']==3

def test_api_upload_mapping_query_exports_and_downloads(store, monkeypatch):
    monkeypatch.setattr(main,'store',store)
    monkeypatch.setattr(main,'PUBLIC_MODE',False)
    c=TestClient(main.app)
    assert c.get('/api/health').json()['status']=='ok'
    response=c.post('/api/uploads',files={'files':('test.csv',b'steel_grade,exit_temp,temp_drop,rough_thickness\nA,1200,100,35\nA,1200,120,40\nA,1200,125,45\n','text/csv')})
    assert response.status_code==200
    u=response.json()[0]
    spec=ImportSpec(name='api test',units_confirmed=True,tables=[table(u)])
    meta=c.post('/api/datasets/import',json=spec.model_dump()).json()
    q=c.post(f'/api/datasets/{meta["id"]}/query',json={}).json()
    assert q['total']==3
    analysis=c.post(f'/api/datasets/{meta["id"]}/analyses',json=AnalysisSpec(steel_grade='A',controls={'exit_temp':[1190,1210]},bins=[30,38,50]).model_dump())
    assert analysis.status_code==200,analysis.text
    result=analysis.json()
    assert c.get(result['artifacts']['figure.png']).headers['content-type']=='image/png'
    exported=c.post(f'/api/datasets/{meta["id"]}/export',json=Filters().model_dump())
    assert len(pd.read_csv(io.BytesIO(exported.content)))==3
    assert c.get(f'/api/analyses/{result["id"]}/artifacts/unexpected.txt').status_code==404

def test_large_dataset_aggregation_and_bounded_payload(store):
    meta=store.save_dataset(synthetic_dataframe(76000),'规模验证模拟数据','simulated')
    q=store.query(meta['id'],Query(page=50))
    assert q['total']==75998
    assert len(q['records'])==30 and len(q['scatter'])<=2500
    assert sum(g['value'] for g in q['grades'])==q['total']
    assert q['records'][0]['record_id']!=q['selected']['record_id']

def test_scatter_selection_locates_matching_table_page(store,dataset):
    first=store.query(dataset['id'],Query())
    target=first['scatter'][-1][2]
    q=store.query(dataset['id'],Query(selected_id=target,locate_selected=True))
    assert q['selected']['record_id']==target
    assert target in {r['record_id'] for r in q['records']}

def test_header_row_and_blank_rows_preserve_original_excel_row(store):
    u=store.save_upload('rows.csv',b'description\nsteel_grade,temp_drop\nA,140\n,\nB,150\n',header_row=1)
    t=table(u)
    t.header_row=1
    meta=store.import_data(ImportSpec(name='rows',units_confirmed=True,tables=[t]))
    d,_=store.get(meta['id'])
    assert d.source_row.tolist()==[3,5]

def test_units_confirmation_conversion_and_bad_numbers(store):
    u=make_upload(store,'板坯编号,粗轧温降,出炉温度,粗轧过程时间\nS1,150,1473.15,3\nS2,bad,1473.15,4\n')
    t=table(u,units={'temp_drop':'K','exit_temp':'K','process_time':'min'})
    with pytest.raises(ValueError,match='确认'):
        store.import_data(ImportSpec(name='bad',units_confirmed=False,tables=[t]))
    meta=store.import_data(ImportSpec(name='converted',units_confirmed=True,tables=[t]))
    d,_=store.get(meta['id'])
    assert d.temp_drop.iloc[0]==150
    assert d.exit_temp.iloc[0]==pytest.approx(1200)
    assert d.process_time.iloc[0]==180
    assert bool(d.invalid.iloc[1])

def test_analysis_does_not_guess_comparable_conditions(store,dataset):
    for controls in [{},{'exit_temp':[None,1220]},{'exit_temp':[1180,1220],'temp_drop':[100,200]}]:
        with pytest.raises(ValueError):
            run_analysis(store,dataset['id'],AnalysisSpec(steel_grade='DEMO-A',controls=controls,bins=[30,38,50]))
