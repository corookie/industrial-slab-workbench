import hashlib
import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from scipy.stats import norm

from app import main
from app.analysis import run_analysis
from app.data import Store, synthetic_dataframe
from app.relationships import calculate_relationships
from app.schema import AnalysisSpec, Filters


def confounded_frame(n=600):
    rng = np.random.default_rng(42)
    thickness = rng.uniform(30,50,n)
    time = 160 + 3*thickness + rng.normal(0,10,n)
    temperature = rng.uniform(1180,1220,n)
    # Orthogonalize errors so known coefficients are recovered exactly, while
    # heteroskedastic residuals exercise the independent HC3 covariance check.
    design = np.column_stack([np.ones(n),thickness,time,temperature])
    errors = rng.normal(0,1,n)*(1+(thickness-30)/5)
    errors -= np.sum(design * np.linalg.lstsq(design,errors,rcond=None)[0],axis=1)
    return pd.DataFrame({'rough_thickness':thickness,'process_time':time,'exit_temp':temperature,
                         'temp_drop':500-2*thickness+.8*time-.3*temperature+errors})


def test_known_coefficients_units_confounding_and_independent_hc3():
    frame = confounded_frame()
    result, complete, model = calculate_relationships(frame,'rough_thickness',['process_time','exit_temp'],2)
    rows = {r['field']:r for r in result['rows']}
    assert len(complete)==600 and result['excluded_missing']==0
    assert rows['rough_thickness']['slope_per_unit']==pytest.approx(-2)
    assert rows['rough_thickness']['adjusted_change']==pytest.approx(-4)
    assert rows['process_time']['adjusted_change']==pytest.approx(8)  # per 10 s
    assert rows['exit_temp']['adjusted_change']==pytest.approx(-3)  # per 10 °C
    assert rows['rough_thickness']['unadjusted_change']>0  # confounding reverses the marginal sign
    # A different, unstandardized design independently verifies robust covariance.
    x = np.column_stack([np.ones(len(frame)),frame[['rough_thickness','process_time','exit_temp']]])
    inv = np.linalg.inv(np.einsum('ni,nj->ij',x,x))
    coef = np.linalg.lstsq(x,frame.temp_drop,rcond=None)[0]
    residual = frame.temp_drop.to_numpy()-np.sum(x*coef,axis=1)
    h = np.einsum('ij,jk,ik->i',x,inv,x)
    meat = sum((residual[i]/(1-h[i]))**2 * np.outer(row,row) for i,row in enumerate(x))
    cov = np.einsum('ij,jk,kl->il',inv,meat,inv)
    half = norm.ppf(.975)*np.sqrt(cov[1,1])*2
    assert rows['rough_thickness']['ci95_low']==pytest.approx(-4-half,rel=1e-7)
    assert rows['rough_thickness']['ci95_high']==pytest.approx(-4+half,rel=1e-7)
    again,_,_=calculate_relationships(frame,'rough_thickness',['process_time','exit_temp'],2)
    assert again==result


def test_missing_constants_collinear_low_n_and_out_of_support():
    frame = confounded_frame(200)
    frame.loc[:9,'process_time']=np.nan
    result, complete,_=calculate_relationships(frame,'rough_thickness',['process_time'])
    assert result['n']==190 and result['excluded_missing']==10
    assert result['rows'][0]['n']==result['rows'][1]['n']==len(complete)
    frame['width']=1200
    result,_,_=calculate_relationships(frame,'rough_thickness',['width'])
    assert result['rows'][1]['status']=='unavailable'
    assert result['rows'][1]['adjusted_change'] is None
    frame['width']=frame.rough_thickness*2
    result,_,model=calculate_relationships(frame,'rough_thickness',['width'])
    assert model is None and all(r['adjusted_change'] is None for r in result['rows'])
    assert any('共线' in w for w in result['warnings'])
    result,_,model=calculate_relationships(frame.iloc[:10],'rough_thickness',[])
    assert model is None and '不足' in result['rows'][0]['reason']
    result,_,_=calculate_relationships(confounded_frame(),'rough_thickness',['process_time','exit_temp'],100)
    assert result['rows'][0]['status']=='unsupported_step'
    constant_target=confounded_frame();constant_target['temp_drop']=140
    result,_,model=calculate_relationships(constant_target,'rough_thickness',[])
    assert model is None and result['rows'][0]['adjusted_change'] is None
    exploratory,_,_=calculate_relationships(confounded_frame(35),'rough_thickness',[])
    assert exploratory['rows'][0]['status']=='exploratory'
    for step in [0,-1,float('nan'),float('inf')]:
        with pytest.raises(ValidationError):
            AnalysisSpec(steel_grade='A',bins=[30,40,50],effect_step=step)
    with pytest.raises(ValidationError):
        AnalysisSpec(steel_grade='A',bins=[30,40,50],relationship_fields=['rough_temp'])


@pytest.mark.parametrize('variable,bins,controls,step',[
    ('rough_thickness',[30,40,50],{'exit_temp':[1180,1220]},1),
    ('process_time',[200,260,350],{'exit_temp':[1180,1220],'rough_thickness':[30,50]},10),
    ('exit_temp',[1180,1200,1220],{'rough_thickness':[30,50],'process_time':[200,350]},10),
])
def test_scope_multivariable_reports_exports_and_rerun(tmp_path,variable,bins,controls,step,monkeypatch):
    store=Store(tmp_path)
    frame=synthetic_dataframe(600)
    known=confounded_frame()
    for k in known:frame[k]=known[k]
    frame['steel_grade']='A'
    frame['width']=np.linspace(1000,1400,len(frame))
    meta=store.save_dataset(frame,'测试模拟关系','simulated')
    spec=AnalysisSpec(steel_grade='A',variable=variable,bins=bins,controls=controls,
                      filters=Filters(ranges={'width':[1100,1350]}),
                      relationship_fields=['rough_thickness','process_time','exit_temp'],effect_step=step)
    result=run_analysis(store,meta['id'],spec)
    folder=store.root/'analyses'/result['id']
    work=pd.read_csv(folder/'samples.csv')
    model_frame=pd.read_csv(folder/'relationship_samples.csv')
    assert len(work)==result['counts']['analyzed']==sum(g['n'] for g in result['groups'])
    assert set(model_frame.record_id)<=set(work.record_id)
    assert len(model_frame)==result['relationships']['n']
    assert work[variable].between(bins[0],bins[-1]).all()
    assert work.width.between(1100,1350).all()
    assert hashlib.sha256((folder/'relationship_samples.csv').read_bytes()).hexdigest()==result['relationships']['samples_sha256']
    assert all(k in result['artifacts'] for k in ['relationship.png','relationship.pdf','relationship.svg','relationships.csv'])
    html_report=(folder/'report.html').read_text()
    assert all(term in html_report for term in ['变量与温降的数值关系','观测下限','VIF','估计状态','共同样本量'])
    assert '95%' in (folder/'report.md').read_text()
    with zipfile.ZipFile(folder/'bundle.zip') as z:
        assert set(['relationships.csv','relationship_samples.csv','relationship.png'])<=set(z.namelist())
    again=run_analysis(store,meta['id'],AnalysisSpec(**result['parameters']))
    assert result['relationships']==again['relationships']
    assert result['parameter_sha256']==again['parameter_sha256']
    monkeypatch.setattr(main,'store',store);monkeypatch.setattr(main,'PUBLIC_MODE',False)
    client=TestClient(main.app)
    csv=client.get(result['artifacts']['relationships.csv'])
    assert csv.status_code==200
    exported=pd.read_csv(io.StringIO(csv.text))
    assert exported.adjusted_change.to_numpy()==pytest.approx([r['adjusted_change'] for r in result['relationships']['rows']])
    with pytest.raises(ValueError):
        run_analysis(store,meta['id'],spec.model_copy(update={'controls':{'rough_temp':[800,1200]}}))
    with pytest.raises(ValueError, match='后续阶段'):
        run_analysis(store,meta['id'],spec.model_copy(update={'relationship_fields':['rolling_thickness']}))


def test_temperature_identity_warning_is_reported(tmp_path):
    store=Store(tmp_path)
    frame=synthetic_dataframe(400)
    frame['steel_grade']='A'
    frame.loc[:49,'rough_temp']=frame.loc[:49,'rough_temp']-12
    meta=store.save_dataset(frame,'温降口径检查','simulated')
    result=run_analysis(store,meta['id'],AnalysisSpec(steel_grade='A',controls={'exit_temp':[1100,1300]},bins=[20,38,42,100],relationship_fields=['rough_thickness','process_time']))
    check=result['relationships']['temperature_identity_check']
    assert check['checked']>50 and check['mismatch_gt_3c']>=40
    assert any('温降字段口径核对' in w for w in result['relationships']['warnings'])
    assert '温降字段口径核对' in (store.root/'analyses'/result['id']/'report.html').read_text()
