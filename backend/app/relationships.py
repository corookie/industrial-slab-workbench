"""Descriptive linear associations on a saved analysis scope, never causal effects."""
import numpy as np
import pandas as pd
from scipy.stats import norm

from .schema import FIELDS

DEFAULT_STEPS = {'rough_thickness': 1, 'thickness': 1, 'rolling_thickness': 1,
                 'process_time': 10, 'exit_temp': 10, 'furnace_time': 10,
                 'width': 100, 'charge_temp': 50, 'length': 1000, 'weight': 100}
METHOD = '含截距普通最小二乘；HC3 异方差稳健协方差；95% 渐近正态区间'
LIMITATION = '线性系数表示本次样本范围内的平均统计关联，不是因果效应；HC3 不校正连续生产记录的时间相关性，区间依赖样本独立假设，各变量区间未作多重比较校正；斜率是观测范围内的线性近似。'


def fit_linear(frame, fields):
    """Standardize for numerical stability; return coefficients in original units."""
    if frame.temp_drop.std(ddof=0) <= 1e-12:
        return None, '当前样本温降没有变化，无法估计有意义的关系区间'
    raw = frame[fields].to_numpy(dtype=float)
    center, scale = raw.mean(axis=0), raw.std(axis=0)
    if np.any(scale <= 1e-12):
        return None, '变量在当前样本中不变化'
    design = np.column_stack([np.ones(len(frame)), (raw-center)/scale])
    n, p = design.shape
    if n < max(20, 5*p):
        return None, f'有效样本不足：至少需要 {max(20, 5*p)} 条'
    if np.linalg.matrix_rank(design) < p or np.linalg.cond(design) > 1e8:
        return None, '所选变量完全或近乎共线，请减少重复变量'
    gram_inv = np.linalg.inv(np.einsum('ni,nj->ij', design, design))
    beta = np.linalg.lstsq(design, frame.temp_drop.to_numpy(dtype=float), rcond=None)[0]
    prediction = np.einsum('ni,i->n', design, beta)
    residual = frame.temp_drop.to_numpy(dtype=float) - prediction
    leverage = np.einsum('ni,ij,nj->n', design, gram_inv, design)
    if np.any(1-leverage < 1e-8):
        return None, '存在几乎完全决定拟合的样本，无法稳定估计区间'
    weighted = design * (residual/(1-leverage))[:, None]
    covariance = np.einsum('ij,jk,kl->il', gram_inv, np.einsum('ni,nj->ij', weighted, weighted), gram_inv)
    if not np.isfinite(beta).all() or not np.isfinite(covariance).all():
        return None, '数值计算不稳定，请缩小范围或减少变量'
    se = np.sqrt(np.maximum(0, np.diag(covariance)[1:]))/scale
    slopes = beta[1:]/scale
    total = float(np.sum((frame.temp_drop-frame.temp_drop.mean())**2))
    # VIF of standardized predictors; intercept is orthogonal to their means.
    vif = np.diag(gram_inv)[1:]*n
    mse = float(np.dot(residual,residual)/(n-p))
    cook = np.square(residual)/(p*mse) * leverage/np.square(1-leverage) if mse > 1e-12 else np.zeros(n)
    return {'slopes': slopes, 'se': se, 'vif': vif, 'influential_count': int((cook > 4/n).sum()),
            'intercept': float(beta[0]-np.dot(slopes, center)), 'n': n,
            'r2': float(1-np.dot(residual,residual)/total) if total > 1e-12 else None,
            'residual_sd': float(np.sqrt(mse)),
            'center': center, 'scale': scale, 'beta': beta, 'covariance': covariance}, None


def calculate_relationships(work, variable, fields, effect_step=None):
    fields = list(dict.fromkeys([variable, *fields]))
    missing = [k for k in fields if k not in work or not np.isfinite(pd.to_numeric(work[k], errors='coerce')).any()]
    usable = [k for k in fields if k not in missing]
    complete = work.copy()
    if usable:
        values = complete[[*usable, 'temp_drop']].apply(pd.to_numeric, errors='coerce')
        complete = complete[np.isfinite(values.to_numpy(dtype=float)).all(axis=1)].copy()
    else:
        complete = complete.iloc[:0].copy()
    constants = [k for k in usable if len(complete) and complete[k].nunique() < 2]
    fitted = [k for k in usable if k not in constants]
    model, reason = fit_linear(complete, fitted) if fitted and len(complete) else (None, '没有足够的完整数值样本')
    warnings = []
    if missing:
        warnings.append('未估计缺失变量：'+'、'.join(FIELDS[k]['label'] for k in missing))
    if constants:
        warnings.append('当前工况内不变化，未估计：'+'、'.join(FIELDS[k]['label'] for k in constants))
    if reason:
        warnings.append(reason)
    rows = []
    z = float(norm.ppf(.975))
    for field in fields:
        step = float(effect_step if field == variable and effect_step is not None else DEFAULT_STEPS[field])
        row = {'field': field, 'label': FIELDS[field]['label'], 'unit': FIELDS[field]['unit'], 'step': step,
               'n': len(complete), 'range_min': None, 'range_max': None,
               'unadjusted_change': None, 'adjusted_change': None, 'ci95_low': None, 'ci95_high': None,
               'slope_per_unit': None, 'vif': None, 'status': 'unavailable', 'reason': '', 'interpretation': ''}
        if field in missing:
            row['reason'] = '字段缺失'
        elif field in constants:
            row['range_min'] = row['range_max'] = float(complete[field].iloc[0])
            row['reason'] = '当前样本中没有变化'
        elif not len(complete):
            row['reason'] = '没有完整样本'
        else:
            row['range_min'], row['range_max'] = float(complete[field].min()), float(complete[field].max())
            simple, simple_reason = fit_linear(complete, [field])
            if simple:
                row['unadjusted_change'] = float(simple['slopes'][0]*step)
            if model:
                i = fitted.index(field)
                change, half = float(model['slopes'][i]*step), float(z*model['se'][i]*step)
                row.update(adjusted_change=change, ci95_low=change-half, ci95_high=change+half,
                           slope_per_unit=float(model['slopes'][i]), vif=float(model['vif'][i]), status='estimated')
                if row['vif'] >= 10:
                    row['status'], row['reason'] = 'unstable', '变量相关性强，系数不稳定（VIF ≥ 10）'
                elif step > row['range_max']-row['range_min']+1e-9:
                    row['status'], row['reason'] = 'unsupported_step', '增量大于观测跨度，请减小增量'
                elif len(complete) < 50:
                    row['status'], row['reason'] = 'exploratory', '完整样本少于 50 条，仅供探索'
                elif row['ci95_low'] <= 0 <= row['ci95_high']:
                    row['status'], row['reason'] = 'uncertain', '区间跨越 0，变化方向不明确'
                direction = '增加' if change >= 0 else '减少'
                row['interpretation'] = f'{row["label"]}每增加 {step:g} {row["unit"]}，拟合温降平均{direction} {abs(change):.2f} °C'
            else:
                row['reason'] = reason or simple_reason
        rows.append(row)
    if any(row['vif'] is not None and row['vif'] >= 10 for row in rows):
        warnings.append('存在强相关变量，部分校正系数不稳定；请减少重复变量后复核')
    if model and model['influential_count']:
        warnings.append(f'有 {model["influential_count"]} 条记录的 Cook 距离超过 4/n 参考线，系数可能受极端观测影响；记录未自动剔除')
    primary = next(row for row in rows if row['field'] == variable)
    if primary['status'] == 'estimated':
        explanation = primary['interpretation']+'。这是校正表中其他变量后的线性关联估计。'
    elif primary['adjusted_change'] is not None:
        explanation = primary['interpretation']+'；'+primary['reason']+'，暂不作明确方向结论。'
    else:
        explanation = FIELDS[variable]['label']+'暂不能给出可靠的单位变化关系：'+primary['reason']+'。'
    result = {'method': METHOD, 'limitation': LIMITATION, 'fields': fields, 'fitted_fields': fitted if model else [],
              'n': len(complete), 'excluded_missing': len(work)-len(complete), 'scope_n': len(work),
              'rows': rows, 'r2_in_sample': model['r2'] if model else None,
              'residual_sd': model['residual_sd'] if model else None,
              'influential_count': model['influential_count'] if model else None,
              'intercept': model['intercept'] if model else None,
              'warnings': warnings, 'explanation': explanation,
              'ci_label': '校正系数的 95% HC3 渐近正态区间（样本独立假设）'}
    return result, complete, model
