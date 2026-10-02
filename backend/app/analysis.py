import base64
import hashlib
import html
import itertools
import json
import platform
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
import scipy
from scipy.stats import t

from .data import Store, apply_filters, fingerprint, json_safe, write_json
from .schema import AnalysisSpec, FIELDS, Filters, NUMERIC, VARIABLES
from .relationships import calculate_relationships
from .privacy import NOTICE

PLOT_LOCK = threading.Lock()
ERROR_LABELS = {'sd': '误差条：组内样本标准差（ddof=1）', 'ci95': '误差条：均值的 95% t 置信区间（独立样本假设）'}
LIMIT = '结果仅描述当前钢种、筛选条件与分组口径下的关联和均值差异，不能直接推断物理因果；区间筛选不保证各组工况完全一致。'

def calculate_groups(d: pd.DataFrame, variable: str, bins: list[float]):
    if any(not np.isfinite(v) for v in bins) or any(a >= b for a, b in zip(bins, bins[1:])):
        raise ValueError('分组边界必须是严格递增的有限数值')
    work = d.dropna(subset=[variable, 'temp_drop']).copy()
    work = work[(work[variable] >= bins[0]) & (work[variable] <= bins[-1])].copy()
    groups = np.searchsorted(bins, work[variable].to_numpy(), side='right') - 1
    # Internal boundary belongs to the next interval; the final upper edge is inclusive.
    groups = np.minimum(groups, len(bins)-2)
    work['group_index'] = groups
    rows = []
    for i, (lo, hi) in enumerate(zip(bins, bins[1:])):
        sub = work[work['group_index'] == i]
        values = sub['temp_drop']
        n = len(sub)
        mean = float(values.mean()) if n else None
        sd = float(values.std(ddof=1)) if n >= 2 else None
        se = sd / np.sqrt(n) if sd is not None else None
        half = float(t.ppf(.975, n-1) * se) if se is not None else None
        controls = {k: {'n': int(sub[k].notna().sum()), 'mean': sub[k].mean(), 'min': sub[k].min(), 'max': sub[k].max()}
                    for k in ['exit_temp', 'process_time', 'furnace_time', 'width', 'thickness', 'charge_temp'] if sub[k].notna().any()}
        rows.append({'index': i, 'label': f'[{lo:g}, {hi:g}{"]" if i == len(bins)-2 else ")"}', 'lower': lo, 'upper': hi,
                     'n': n, 'mean': mean, 'sd': sd, 'se': se,
                     'median': values.median(), 'ci95_low': mean-half if half is not None else None,
                     'ci95_high': mean+half if half is not None else None, 'ci95_half': half, 'variable_mean': sub[variable].mean(), 'controls': controls})
    pairs = []
    for a, b in itertools.combinations(rows, 2):
        if a['n'] and b['n']:
            pairs.append({'a': a['label'], 'b': b['label'], 'n_a': a['n'], 'n_b': b['n'],
                          'mean_difference_b_minus_a': b['mean']-a['mean']})
    return work, json_safe(rows), pairs

def condition_text(spec: AnalysisSpec):
    parts = [f'钢种：{spec.steel_grade}']
    for label, ranges in [('当前筛选', spec.filters.ranges), ('控制条件', spec.controls)]:
        for key, bounds in ranges.items():
            parts.append(f'{label} {FIELDS[key]["label"]}：{bounds[0] if bounds[0] is not None else "不限"}—{bounds[1] if bounds[1] is not None else "不限"} {FIELDS[key]["unit"]}')
    if spec.filters.date_start or spec.filters.date_end:
        parts.append(f'时间：{spec.filters.date_start or "不限"}—{spec.filters.date_end or "不限"}')
    parts.append('异常记录：' + ('排除' if spec.filters.exclude_invalid else '包含'))
    return parts

def plot_report(folder, work, result, spec, relation_work, model):
    with PLOT_LOCK:
        candidates = ['/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                      '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
        family = 'DejaVu Sans'
        for path in candidates:
            if Path(path).exists():
                font_manager.fontManager.addfont(path)
                family = font_manager.FontProperties(fname=path).get_name()
                break
        with plt.rc_context({'font.family': family, 'axes.unicode_minus': False, 'font.size': 10,
                             'svg.fonttype': 'none', 'pdf.fonttype': 42, 'axes.spines.top': False, 'axes.spines.right': False}):
            fig, axs = plt.subplots(2, 2, figsize=(13, 9.2))
            rows = result['groups']
            x = np.arange(len(rows))
            labels = [g['label'] for g in rows]
            means = [g['mean'] if g['mean'] is not None else np.nan for g in rows]
            errors = [g['sd'] if spec.error_bar == 'sd' else g['ci95_half'] for g in rows]
            axs[0, 0].bar(x, means, color='#286a9d', width=.65)
            valid = [i for i, e in enumerate(errors) if e is not None]
            axs[0, 0].errorbar(valid, [means[i] for i in valid], yerr=[errors[i] for i in valid], fmt='none', capsize=5, color='#15344f')
            for i, g in enumerate(rows):
                cap = (means[i] + (errors[i] or 0)) if g['n'] else 0
                axs[0, 0].annotate(f'n={g["n"]}', (i, cap), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=9)
            axs[0, 0].margins(y=.18)
            axs[0, 0].set_title('A  平均温降与误差条', loc='left', fontweight='bold')
            axs[0, 0].set_ylabel('粗轧温降 / °C')
            values, positions = [], []
            for i in range(len(rows)):
                vals = work.loc[work['group_index'] == i, 'temp_drop'].to_numpy()
                if len(vals):
                    values.append(vals)
                    positions.append(i)
            axs[0, 1].boxplot(values, positions=positions, widths=.55, patch_artist=True,
                              boxprops={'facecolor': '#d9e8f3', 'edgecolor': '#286a9d'},
                              medianprops={'color': '#a34928'}, flierprops={'markersize': 2, 'alpha': .3})
            axs[0, 1].set_title('B  组内分布（箱线图）', loc='left', fontweight='bold')
            axs[0, 1].set_ylabel('粗轧温降 / °C')
            axs[1, 0].bar(x, [g['n'] for g in rows], color='#6d8799')
            axs[1, 0].set_title('C  各组样本量', loc='left', fontweight='bold')
            axs[1, 0].set_ylabel('记录数')
            exit_values, exit_positions = [], []
            for i in range(len(rows)):
                vals = work.loc[work['group_index'] == i, 'exit_temp'].dropna().to_numpy()
                if len(vals):
                    exit_values.append(vals)
                    exit_positions.append(i)
            axs[1, 1].boxplot(exit_values, positions=exit_positions, widths=.55, patch_artist=True,
                              boxprops={'facecolor': '#fae7d6', 'edgecolor': '#b7753f'}, flierprops={'markersize': 2, 'alpha': .3})
            axs[1, 1].set_title('D  控制工况检查：各组出炉温度', loc='left', fontweight='bold')
            axs[1, 1].set_ylabel('出炉温度 / °C')
            for ax in axs.flat:
                ax.set_xticks(x, labels, rotation=20)
                ax.set_xlim(-.6, len(rows)-.4)
                ax.set_xlabel(FIELDS[spec.variable]['label'] + '区间 / ' + FIELDS[spec.variable]['unit'])
                ax.grid(axis='y', color='#e8edf0', linewidth=.6)
                ax.set_axisbelow(True)
            release = result.get('release') or {}
            if release.get('data_origin') == 'independent_simulation':
                source_label = '完全独立模拟示例，非工业结论'
            else:
                source_label = {'real': '真实上传数据', 'sanitized': '脱敏合成演示，非工业结论'}.get(result['source_kind'], '模拟数据，非工业结论')
            fig.suptitle(f'{FIELDS[spec.variable]["label"]}分组与粗轧温降差异 | {source_label}', fontsize=16, fontweight='bold', x=.06, ha='left', y=.98)
            conditions = '；'.join(condition_text(spec))
            import textwrap
            fig.text(.06, .93, '\n'.join(textwrap.wrap(conditions, width=98)), fontsize=9, va='top')
            fig.text(.06,.075,ERROR_LABELS[spec.error_bar],fontsize=8,color='#536474')
            fig.text(.06, .025, f'有效分组样本 n={len(work)}；{LIMIT}\n数据指纹：{result["dataset_sha256"][:16]}  参数指纹：{result["parameter_sha256"][:16]}', fontsize=8, color='#536474')
            fig.subplots_adjust(top=.82, bottom=.16, hspace=.65, wspace=.25)
            for extension in ['png', 'svg', 'pdf']:
                fig.savefig(folder / f'figure.{extension}', dpi=180, facecolor='white')
            plt.close(fig)
            relationship = result['relationships']
            fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
            ax, residual_ax = axes
            unit = FIELDS[spec.variable]['unit']
            ax.set_xlabel(f'{FIELDS[spec.variable]["label"]} / {unit}')
            ax.set_ylabel('粗轧温降 / °C')
            ax.set_title('A  校正关系（其他变量取样本均值）', loc='left')
            residual_ax.set_title('B  残差与拟合值', loc='left')
            residual_ax.set_xlabel('拟合温降 / °C'); residual_ax.set_ylabel('残差 / °C')
            if len(relation_work):
                # Draw a bounded subset, but fit and estimate intervals on every complete record.
                display = relation_work.iloc[np.linspace(0,len(relation_work)-1,min(2000,len(relation_work)),dtype=int)]
                ax.scatter(display[spec.variable], display.temp_drop, s=9, alpha=.25, color='#78905e', label='实际观测（绘图最多 2,000 点）')
            if model and spec.variable in relationship['fitted_fields']:
                fields = relationship['fitted_fields']
                i = fields.index(spec.variable)
                grid = np.linspace(relation_work[spec.variable].min(), relation_work[spec.variable].max(), 150)
                design = np.zeros((len(grid),len(fields)+1)); design[:,0] = 1
                design[:,i+1] = (grid-model['center'][i])/model['scale'][i]
                pred = np.einsum('ni,i->n',design,model['beta'])
                half = 1.959963984540054 * np.sqrt(np.maximum(0,np.einsum('ni,ij,nj->n',design,model['covariance'],design)))
                ax.plot(grid,pred,color='#cb6b43',label='校正后线性拟合')
                ax.fill_between(grid,pred-half,pred+half,color='#cb6b43',alpha=.18,label='均值拟合 95% HC3 区间')
                full_design = np.column_stack([np.ones(len(relation_work)),(relation_work[fields].to_numpy()-model['center'])/model['scale']])
                fitted = np.einsum('ni,i->n',full_design,model['beta'])
                idx = np.linspace(0,len(relation_work)-1,min(2000,len(relation_work)),dtype=int)
                residual_ax.scatter(fitted[idx],(relation_work.temp_drop.to_numpy()-fitted)[idx],s=9,alpha=.3,color='#527680')
                residual_ax.axhline(0,color='#cb6b43',lw=1)
                ax.legend(fontsize=8)
            else:
                ax.text(.5,.85,relationship['explanation'],ha='center',wrap=True,transform=ax.transAxes,fontsize=9)
                residual_ax.text(.5,.5,'未得到可用的校正模型',ha='center',transform=residual_ax.transAxes)
            for a in axes:
                a.grid(color='#e8edf0',linewidth=.6); a.set_axisbelow(True)
            fig.suptitle(f'{FIELDS[spec.variable]["label"]}与粗轧温降的数值关系 | {source_label}',ha='left',x=.06,fontsize=14)
            fig.text(.06,.91,f'完整样本 n={relationship["n"]} / 分组样本 {len(work)}；'+conditions,fontsize=8,wrap=True)
            fig.text(.06,.025,'线性关联，非因果效应；阴影为均值拟合区间，不是单条记录预测区间；HC3 未校正时间自相关。',fontsize=8,color='#536474')
            fig.subplots_adjust(top=.79,bottom=.18,wspace=.3)
            for extension in ['png','svg','pdf']:
                fig.savefig(folder / f'relationship.{extension}',dpi=180,facecolor='white')
            plt.close(fig)

def run_analysis(store: Store, dataset_id: str, spec: AnalysisSpec):
    original, meta = store.get(dataset_id)
    actual_sha = hashlib.sha256((store.root / 'datasets' / dataset_id / 'normalized.csv').read_bytes()).hexdigest()
    if actual_sha != meta['sha256']:
        raise ValueError('数据文件已改变，请重新导入，避免使用过期指纹')
    if spec.variable not in meta['available'] or 'temp_drop' not in meta['available']:
        raise ValueError('当前数据缺少分析变量或粗轧温降')
    if spec.steel_grade == '未提供钢种':
        raise ValueError('该任务需要钢种字段，请先完成映射')
    if spec.variable != 'exit_temp' and ('exit_temp' not in spec.controls or len(spec.controls['exit_temp']) != 2 or None in spec.controls['exit_temp']):
        raise ValueError('请设置相近出炉温度的上下限，作为可比工况控制条件')
    if not spec.controls:
        raise ValueError('请至少设置一个其他变量的控制范围')
    if any(k not in VARIABLES or k not in meta['available'] for k in spec.controls):
        raise ValueError('控制变量须为已有工况字段，不能使用温降或轧后温度')
    if any(len(v)!=2 or any(x is None or not np.isfinite(x) for x in v) for v in spec.controls.values()):
        raise ValueError('控制范围须包含有限的上下限')
    requested = spec.relationship_fields if spec.relationship_fields is not None else [k for k in ['rough_thickness','process_time','exit_temp','furnace_time','width'] if k in meta['available']]
    if any(k not in meta['available'] for k in requested):
        raise ValueError('量化变量在当前数据中不存在，请重新选择')
    relation_fields = list(dict.fromkeys([spec.variable,*requested,*spec.controls]))
    if spec.variable != 'rolling_thickness' and ('rolling_thickness' in relation_fields or 'rolling_thickness' in spec.controls):
        raise ValueError('轧制厚度属于后续阶段，不能作为粗轧分析的校正变量；可单独选择它做描述性分析')
    if spec.variable in spec.controls or 'temp_drop' in spec.controls:
        raise ValueError('控制变量不能包含分组变量或作为结果的温降')
    scope = apply_filters(original, spec.filters)
    controlled = apply_filters(scope, Filters(grades=[spec.steel_grade], ranges=spec.controls, exclude_invalid=False))
    work, groups, differences = calculate_groups(controlled, spec.variable, spec.bins)
    if len(work) < 2:
        raise ValueError('当前工况及分组区间内有效样本不足 2 条，请调整筛选或区间')
    ident = uuid.uuid4().hex
    folder = store.root / 'analyses' / ident
    folder.mkdir()
    params = spec.model_dump()
    warnings = []
    if len([g for g in groups if g['n']]) < 2:
        warnings.append('仅一个分组有样本，无法进行组间比较')
    if any(g['n'] < 10 for g in groups):
        warnings.append('部分分组样本少于 10 条或为空，请结合样本量解释结果')
    if spec.error_bar == 'ci95':
        warnings.append('95% t 区间基于独立同分布样本假设，连续生产记录可能存在自相关，首版未校正时间相关性')
    release_notice = (meta.get('release') or {}).get('notice')
    if release_notice:
        warnings.append(release_notice)
    elif meta['source_kind'] == 'simulated':
        warnings.append('模拟数据包含人为设置的关系，仅用于演示分析流程')
    elif meta['source_kind'] == 'sanitized':
        warnings.append(NOTICE)
    eligible = controlled[[spec.variable, 'temp_drop']].notna().all(axis=1)
    relationships, relation_work, model = calculate_relationships(work, spec.variable, relation_fields, spec.effect_step)
    if spec.variable == 'rolling_thickness':
        relationships['warnings'].append('轧制厚度为后续阶段指标，仅描述统计关联，不能推断其对粗轧温降的影响')
    if 'rough_temp' in meta['available']:
        observed = work[['exit_temp', 'rough_temp', 'temp_drop']].apply(pd.to_numeric, errors='coerce')
        observed = observed[np.isfinite(observed.to_numpy(dtype=float)).all(axis=1)]
        mismatch = int(((observed.exit_temp-observed.rough_temp-observed.temp_drop).abs()>3).sum())
        relationships['temperature_identity_check'] = {'checked': len(observed), 'mismatch_gt_3c': mismatch}
        if mismatch:
            relationships['warnings'].append(f'温降字段口径核对：{len(observed)} 条同时有出炉、粗轧后温度和温降，其中 {mismatch} 条与出炉温度－粗轧后温度相差超过 3 °C；请确认测温点与单位')
    code_sha = hashlib.sha256(b''.join((Path(__file__).parent / name).read_bytes() for name in ['analysis.py', 'relationships.py', 'data.py', 'schema.py', 'privacy.py'])).hexdigest()
    result = {'id': ident, 'dataset_id': dataset_id, 'dataset_name': meta['name'], 'source_kind': meta['source_kind'],
              'created_at': datetime.now(timezone.utc).isoformat(), 'dataset_sha256': meta['sha256'],
              'parameter_sha256': fingerprint(params), 'code_sha256': code_sha, 'parameters': params,
              'scope_sha256': fingerprint({'dataset_sha256': meta['sha256'], 'filters': spec.filters.model_dump()}),
              'counts': {'source': len(original), 'current_scope': len(scope), 'controlled': len(controlled),
                         'missing_analysis_values': int((~eligible).sum()), 'outside_bins': int(eligible.sum()-len(work)), 'analyzed': len(work)},
              'groups': groups, 'differences': differences, 'relationships': relationships, 'warnings': warnings, 'conditions': condition_text(spec),
              'error_bar_label': ERROR_LABELS[spec.error_bar], 'limitation': LIMIT,
              'interval_policy': '左闭右开；最后一个区间包含右端点；缺失值及区间外样本不参与分组',
              'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__, 'matplotlib': matplotlib.__version__, 'scipy': scipy.__version__},
              'provenance': meta['provenance'], 'release': meta.get('release')}
    nonempty = [g for g in groups if g['n']]
    high, low = max(nonempty, key=lambda g: g['mean']), min(nonempty, key=lambda g: g['mean'])
    result['explanation'] = f'当前工况纳入 {len(work):,} 条记录。{high["label"]} {FIELDS[spec.variable]['unit']} 组平均温降最高，为 {high["mean"]:.2f} °C；{low["label"]} {FIELDS[spec.variable]['unit']} 组最低，为 {low["mean"]:.2f} °C。均值最大差为 {high["mean"]-low["mean"]:.2f} °C。该差值为描述性统计，未进行因果估计或显著性检验。'
    work.to_csv(folder / 'samples.csv', index=False, encoding='utf-8-sig')
    result['samples_sha256'] = hashlib.sha256((folder / 'samples.csv').read_bytes()).hexdigest()
    pd.DataFrame([{k: v for k, v in g.items() if k != 'controls'} for g in groups]).to_csv(folder / 'statistics.csv', index=False, encoding='utf-8-sig')
    relation_work.to_csv(folder / 'relationship_samples.csv',index=False,encoding='utf-8-sig')
    relationships['samples_sha256'] = hashlib.sha256((folder/'relationship_samples.csv').read_bytes()).hexdigest()
    pd.DataFrame(relationships['rows']).assign(source_kind=meta['source_kind'], dataset_name=meta['name'], analysis_id=ident, model_samples_sha256=relationships['samples_sha256']).to_csv(folder/'relationships.csv',index=False,encoding='utf-8-sig')
    plot_report(folder, work, result, spec, relation_work, model)
    result['artifacts'] = {name: f'/api/analyses/{ident}/artifacts/{name}' for name in ['figure.png', 'figure.svg', 'figure.pdf', 'relationship.png', 'relationship.svg', 'relationship.pdf', 'relationships.csv', 'relationship_samples.csv', 'report.html', 'report.md', 'statistics.csv', 'samples.csv', 'parameters.json', 'result.json', 'bundle.zip']}
    write_json(folder / 'parameters.json', params)
    write_json(folder / 'result.json', result)
    summary_table = pd.DataFrame([{k: g[k] for k in ['label', 'n', 'mean', 'sd', 'median', 'ci95_low', 'ci95_high']} for g in groups]).rename(columns={'label': '区间 / '+FIELDS[spec.variable]['unit'], 'n': '样本量', 'mean': '平均温降 / °C', 'sd': '样本标准差 / °C', 'median': '中位数 / °C', 'ci95_low': '均值 t95 下限', 'ci95_high': '均值 t95 上限'})
    if spec.error_bar != 'ci95':
        summary_table = summary_table.drop(columns=['均值 t95 下限', '均值 t95 上限'])
    markdown = '\n\n'.join(['# '+FIELDS[spec.variable]['label']+'与粗轧温降分析', f'数据集：{meta["name"]}（{meta["source_kind"]}）', '\n'.join(result['conditions']), result['explanation'], relationships['explanation'], relationships['method'], relationships['limitation'], *relationships['warnings'], pd.DataFrame(relationships['rows']).to_csv(index=False), result['error_bar_label'], result['interval_policy'], LIMIT, '\n'.join(warnings), '分组结果见 statistics.csv；数值关系见 relationships.csv；模型完整样本见 relationship_samples.csv。', json.dumps(result['counts'], ensure_ascii=False), f'数据 SHA256：{meta["sha256"]}\n参数 SHA256：{result["parameter_sha256"]}\n样本 SHA256：{result["samples_sha256"]}\n分析实现 SHA256：{code_sha}'])
    (folder / 'report.md').write_text(markdown, encoding='utf-8')
    embedded = base64.b64encode((folder / 'figure.png').read_bytes()).decode()
    paragraphs = ''.join(f'<p>{html.escape(p)}</p>' for p in [meta['name'], result['source_kind'], *result['conditions'], result['explanation'], relationships['explanation'], relationships['method'], relationships['limitation'], *relationships['warnings'], result['error_bar_label'], result['interval_policy'], *warnings, LIMIT])
    relation_table = pd.DataFrame([{k:r[k] for k in ['label','step','unit','n','range_min','range_max','unadjusted_change','adjusted_change','ci95_low','ci95_high','vif','status','reason']} for r in relationships['rows']]).rename(columns={'label':'变量','step':'增加量','unit':'单位','n':'共同样本量','range_min':'观测下限','range_max':'观测上限','unadjusted_change':'单变量变化 / °C','adjusted_change':'校正后变化 / °C','ci95_low':'95%下限','ci95_high':'95%上限','vif':'VIF','status':'估计状态','reason':'提示'})
    doc = f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>粗轧温降分析报告</title><style>body{{max-width:1100px;margin:40px auto;padding:24px;font:16px/1.7 system-ui;color:#16324f}}img{{width:100%}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d6dfe6;padding:8px;text-align:right}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}@media print{{body{{margin:0}}}}</style><h1>{html.escape(FIELDS[spec.variable]["label"])}与粗轧温降分析</h1>{paragraphs}<h2>变量与温降的数值关系</h2>{relation_table.to_html(index=False, float_format=lambda x:f"{x:.3f}", na_rep="—", escape=True)}<img alt="校正关系与残差" src="data:image/png;base64,{base64.b64encode((folder / "relationship.png").read_bytes()).decode()}"><h2>分组比较</h2><img alt="统计图组" src="data:image/png;base64,{embedded}">{summary_table.to_html(index=False, float_format=lambda x:f"{x:.3f}", na_rep="—", escape=True)}<h2>样本流与复现信息</h2><pre>{html.escape(json.dumps({k:result[k] for k in ["counts", "parameters", "dataset_sha256", "parameter_sha256", "samples_sha256", "code_sha256", "versions"]},ensure_ascii=False,indent=2))}</pre></html>'
    (folder / 'report.html').write_text(doc, encoding='utf-8')
    with zipfile.ZipFile(folder / 'bundle.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for f in folder.iterdir():
            if f.name != 'bundle.zip':
                z.write(f, f.name)
    return json_safe(result)
