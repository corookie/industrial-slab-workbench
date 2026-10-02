"""Keep public demonstration data independent from local production data.

The repository's public service must only load the fixed-parameter simulation
defined below. The older source-derived generator is retained for local,
private review workflows, but its output is deliberately rejected by the
public API.
"""
from pathlib import Path
import hashlib
import json
import secrets

import numpy as np
import pandas as pd

from .data import Store, quality_frame, write_json
from .schema import FIELDS, NUMERIC


# Public GitHub/Render deployment -------------------------------------------------
# These are declared illustrative parameters. They are not calculated from any
# uploaded production file, confidential aggregate, or previous demonstration
# release. Keeping the values in source makes the public data reproducible and
# auditable.
PUBLIC_DEMO_SEED = 26180
PUBLIC_NOTICE = '完全独立模拟示例；使用预设参数生成，未使用任何真实生产记录、汇总统计或脱敏副本；仅用于展示分析流程，不代表工业结论。'
PUBLIC_POLICY = {
    'version': 'independent-synthetic-v1',
    'source_kind': 'simulated',
    'data_origin': 'independent_simulation',
    'grade_labels': 'G01—G05 为虚构演示类别，不对应真实钢种、排名、产量或占比',
    'records_per_grade': 2000,
    'counts': '每类固定 2,000 条，用于页面性能与分组演示，不代表真实产量或比例',
    'values': '使用代码中公开声明的固定参数、随机种子和人为设定的变量关系生成；未读取上传文件或源数据统计',
    'time': '统一虚构演示时间，随机生成；不保留生产时间或记录间隔',
    'traceability': '不包含真实板坯编号、钢种、炉号、文件名、上传路径、源行、源数据指纹或映射',
    'notice': PUBLIC_NOTICE,
    'limitation': '这是完全独立的模拟数据。数值关系仅用于演示分析方法，不能用于推断真实工业过程。',
}
PUBLIC_CSV_COLUMNS = [
    'slab_id', 'steel_grade', 'produced_at',
    'length', 'width', 'thickness', 'rough_thickness', 'rolling_thickness',
    'exit_temp', 'charge_temp', 'rough_temp', 'finish_temp', 'temp_drop',
    'process_time', 'furnace_time', 'weight', 'furnace',
    'source_file', 'source_sheet', 'source_row', 'conversion_issue',
    'data_status', 'invalid', 'quality_note',
]


def create_independent_public_dataframe(seed: int = PUBLIC_DEMO_SEED, per_grade: int = 2000):
    """Create the public G01--G05 example without inspecting a source dataset."""
    if per_grade < 50 or per_grade > 20000:
        raise ValueError('每个公开演示类别的样本量须为 50—20,000 条')

    rng = np.random.default_rng(seed)
    grade_index = np.repeat(np.arange(5), per_grade)
    count = len(grade_index)

    # Deliberately illustrative dimensions and process values. The coefficients
    # below provide a stable data-analysis example only; they do not encode a
    # physical model or an estimate from a production line.
    rough_thickness = np.clip(rng.normal(34 + grade_index * 2.1, 3.2, count), 24, 56)
    exit_temp = np.clip(rng.normal(1198 - grade_index * 3.5, 18, count), 1120, 1270)
    process_time = np.clip(rng.normal(172 + grade_index * 6 + .45 * (rough_thickness - 40), 17, count), 120, 285)
    furnace_time = np.clip(rng.normal(182 + grade_index * 5, 19, count), 120, 275)
    length = np.clip(rng.normal(9800 + grade_index * 140, 420, count), 8200, 11800)
    width = rng.choice([1100, 1250, 1400, 1600], count, p=[.22, .35, .28, .15])
    thickness = rng.choice([210, 230, 250, 280], count, p=[.18, .37, .31, .14])
    rolling_thickness = np.clip(rng.normal(3.4 + grade_index * .12, .75, count), 1.2, 7.5)
    charge_temp = np.clip(rng.normal(390 + grade_index * 18, 78, count), 180, 670)
    grade_effect = np.take(np.array([-5.5, -2.5, 0.0, 2.5, 5.5]), grade_index)
    temp_drop = (126 + .38 * (rough_thickness - 40) + .18 * (process_time - 180)
                 + .11 * (exit_temp - 1190) - .05 * (furnace_time - 185)
                 + grade_effect + rng.normal(0, 7.5, count))
    rough_temp = exit_temp - temp_drop
    finish_temp = rough_temp - rng.normal(108, 14, count)
    weight = length * width * thickness * 7.85e-6

    frame = pd.DataFrame({
        'slab_id': [f'SIM-{i + 1:06d}' for i in range(count)],
        'steel_grade': [f'G{i + 1:02d}' for i in grade_index],
        'produced_at': (pd.Timestamp('2024-07-01') + pd.to_timedelta(rng.integers(0, 31 * 24 * 60, count), unit='min')).strftime('%Y-%m-%dT%H:%M:%S'),
        'length': length.round(0),
        'width': width,
        'thickness': thickness,
        'rough_thickness': rough_thickness.round(2),
        'rolling_thickness': rolling_thickness.round(2),
        'exit_temp': exit_temp.round(2),
        'charge_temp': charge_temp.round(2),
        'rough_temp': rough_temp.round(2),
        'finish_temp': finish_temp.round(2),
        'temp_drop': temp_drop.round(2),
        'process_time': process_time.round(2),
        'furnace_time': furnace_time.round(2),
        'weight': weight.round(0),
        'furnace': None,
        'source_file': '独立模拟示例.csv',
        'source_sheet': '独立生成',
        'source_row': np.arange(count) + 2,
        'conversion_issue': False,
        'data_status': '完全独立模拟示例；非真实生产记录',
    })
    # Shuffle the synthetic records so page order does not imply an artificial
    # grade block, while keeping the fixed seed reproducible.
    return quality_frame(frame.iloc[rng.permutation(count)].reset_index(drop=True))


def canonical_public_csv_bytes(frame: pd.DataFrame):
    """Return the stable byte representation used to authenticate public data."""
    if list(frame.columns) != PUBLIC_CSV_COLUMNS:
        raise ValueError('公开独立模拟示例的字段顺序或字段集合无效')
    return frame.to_csv(index=False, na_rep='', lineterminator='\n').encode('utf-8')


def public_csv_sha256(frame: pd.DataFrame):
    return hashlib.sha256(canonical_public_csv_bytes(frame)).hexdigest()


def write_independent_public_demo(path: Path, seed: int = PUBLIC_DEMO_SEED, per_grade: int = 2000):
    """Freeze the independently generated public example and its release policy."""
    frame = create_independent_public_dataframe(seed=seed, per_grade=per_grade)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\xef\xbb\xbf' + canonical_public_csv_bytes(frame))
    write_json(path.with_suffix('.json'), {
        **PUBLIC_POLICY,
        'seed': seed,
        'records_per_grade': per_grade,
        'csv_sha256': public_csv_sha256(frame),
    })
    return frame


def is_independent_public_release(meta: dict):
    release = meta.get('release') or {}
    return meta.get('source_kind') == 'simulated' and release.get('version') == PUBLIC_POLICY['version']


def save_independent_public_release(store: Store, d: pd.DataFrame):
    meta = store.save_dataset(
        d,
        '公开独立模拟示例 · G01—G05',
        'simulated',
        warnings=[PUBLIC_NOTICE, PUBLIC_POLICY['limitation']],
    )
    counts = d.steel_grade.value_counts()
    meta['release'] = {**PUBLIC_POLICY, 'records_per_grade': int(counts.iloc[0])}
    write_json(store.root / 'datasets' / meta['id'] / 'meta.json', meta)
    return meta


def ensure_public_dataset(store: Store, project: Path):
    """Load only the checked-in independent simulation for public mode."""
    path = project / 'data' / 'examples' / 'public_demo.csv'
    policy_path = path.with_suffix('.json')
    if not path.exists() or not policy_path.exists():
        raise ValueError('缺少公开独立模拟示例文件，公开服务已停止启动以避免加载错误数据')
    try:
        policy = json.loads(policy_path.read_text(encoding='utf-8-sig'))
    except ValueError as exc:
        raise ValueError('公开独立模拟示例的策略文件无法解析') from exc
    if not isinstance(policy, dict) or policy.get('version') != PUBLIC_POLICY['version'] or policy.get('data_origin') != 'independent_simulation':
        raise ValueError('公开演示文件不是完全独立模拟数据，公开服务已停止启动')

    d = pd.read_csv(path, dtype={'slab_id': str, 'steel_grade': str})
    required = set(FIELDS) | {'source_file', 'source_sheet', 'source_row', 'conversion_issue', 'data_status'}
    expected_grades = {f'G{i:02d}' for i in range(1, 6)}
    valid_counts = d.steel_grade.value_counts().to_dict() if 'steel_grade' in d else {}
    if not required <= set(d) or set(d.steel_grade) != expected_grades:
        raise ValueError('公开独立模拟示例字段或类别无效')
    try:
        seed = int(policy.get('seed'))
        records_per_grade = int(policy.get('records_per_grade'))
    except (TypeError, ValueError) as exc:
        raise ValueError('公开独立模拟示例的类别样本量无效') from exc
    if seed != PUBLIC_DEMO_SEED or records_per_grade != PUBLIC_POLICY['records_per_grade']:
        raise ValueError('公开独立模拟示例的固定生成参数无效')
    if any(int(valid_counts.get(grade, 0)) != records_per_grade for grade in expected_grades):
        raise ValueError('公开独立模拟示例的类别样本量无效')
    if not d['data_status'].astype(str).eq('完全独立模拟示例；非真实生产记录').all():
        raise ValueError('公开独立模拟示例的数据标识无效')
    if not d['source_file'].astype(str).eq('独立模拟示例.csv').all() or d['furnace'].notna().any():
        raise ValueError('公开独立模拟示例包含不允许的来源信息')
    expected = create_independent_public_dataframe(seed=seed, per_grade=records_per_grade)
    expected_sha = public_csv_sha256(expected)
    actual_sha = public_csv_sha256(d)
    if policy.get('csv_sha256') != expected_sha or actual_sha != expected_sha:
        raise ValueError('公开独立模拟示例的内容校验失败，公开服务已停止启动')
    existing = next((m for m in store.list_datasets() if is_independent_public_release(m)), None)
    if existing:
        return existing
    return save_independent_public_release(store, d)


# Local-only source-derived review helper ----------------------------------------
# These functions are intentionally not used by ensure_public_dataset. They are
# retained because the local private workflow can review a source-derived draft
# before an owner decides how to handle it outside this repository.
NOTICE = '脱敏合成演示数据；仅取源数据数量前五的钢种类别生成独立记录。编号、日期、样本量及数值已重建，不代表真实生产记录或工业结论。'
POLICY = {
    'version': 'coarse-synthetic-v1', 'source_kind': 'sanitized',
    'top_grades': 5, 'ranking': '源数据非空钢种的全部记录数量；并列按钢种文本排序；生成前一次确定',
    'grade_labels': '匿名代号 G01—G05，代号顺序随机，不表示真实数量排名',
    'records_per_grade': 2000, 'counts': '每类固定演示样本量，不保留真实产量或占比',
    'values': '每类不少于 50 条有效记录的数值列，使用粗粒度中心、离散度和相关性参数重新抽样；极值不保留',
    'time': '统一虚构演示月份，随机日期；不保留真实时间或记录间隔',
    'traceability': '不输出原钢种、炉号、源行、文件名、上传路径、源数据指纹或匿名映射',
    'notice': NOTICE,
    'limitation': '近似统计结构仍可能包含业务信息；未实现差分隐私或形式化披露风险认证。对外发布仍须由数据权属方确认。',
}

# (coarse parameter step, minimum spread, clipping range, displayed precision)
CONFIG = {
    'length': (500, 300, (1000, 20000), 0), 'width': (100, 50, (500, 2500), 0),
    'thickness': (20, 10, (100, 400), 0), 'rough_thickness': (5, 2, (20, 100), 1),
    'rolling_thickness': (1, .5, (.5, 30), 1), 'exit_temp': (25, 10, (900, 1400), 0),
    'charge_temp': (50, 25, (20, 900), 0), 'rough_temp': (25, 10, (600, 1300), 0),
    'finish_temp': (25, 10, (650, 1050), 0), 'temp_drop': (10, 5, (30, 350), 0),
    'process_time': (20, 10, (30, 900), 0), 'furnace_time': (20, 10, (30, 360), 0),
    'weight': (2000, 1000, (1000, 100000), 0),
}


def top_grade_names(d, count=5):
    grades = d['steel_grade'].dropna().astype(str).str.strip()
    grades = grades[(grades != '') & (grades != '未提供钢种')]
    counts = grades.value_counts()
    ranked = sorted(counts.index, key=lambda name: (-int(counts[name]), name))
    if len(ranked) < count:
        raise ValueError(f'需要至少 {count} 个非空钢种类别，当前不足')
    return ranked[:count]


def create_public_dataframe(d, seed=None, per_grade=2000):
    """Create a source-derived draft for local-only review; never public mode."""
    if per_grade < 50 or per_grade > 20000:
        raise ValueError('每个演示钢种的样本量须为 50—20,000 条')
    ranked = top_grade_names(d)
    rng = np.random.default_rng(seed if seed is not None else secrets.randbits(128))
    label_order = rng.permutation(5)
    frames, mapping = [], []
    for rank, name in enumerate(ranked):
        label = f'G{label_order[rank]+1:02d}'
        sub = d.loc[(d.steel_grade == name) & ~d.invalid].copy()
        if len(sub) < 50:
            raise ValueError('前五类别中存在不足 50 条有效记录的钢种，已停止生成')
        columns = [key for key in NUMERIC if sub[key].notna().sum() >= 50]
        corr = sub[columns].corr().fillna(0).to_numpy()
        corr = np.clip(np.round(corr * 4) / 4, -.5, .5) * .7
        np.fill_diagonal(corr, 1)
        eigenvalues, eigenvectors = np.linalg.eigh(corr)
        corr = np.einsum('ij,j,kj->ik', eigenvectors, np.maximum(eigenvalues, .05), eigenvectors)
        scale = np.sqrt(np.diag(corr))
        corr /= np.outer(scale, scale)
        latent = np.einsum('ij,kj->ik', rng.normal(size=(per_grade, len(columns))), np.linalg.cholesky(corr))
        generated = pd.DataFrame(index=range(per_grade))
        for index, key in enumerate(columns):
            step, floor, limits, precision = CONFIG[key]
            values = sub[key].dropna()
            center = np.round(values.median() / step) * step
            spread = max(floor, np.round((values.quantile(.75) - values.quantile(.25)) / 1.349 / step) * step)
            center += rng.choice([-1, 1]) * step * .5
            generated[key] = np.clip(center + spread * latent[:, index], *limits).round(precision)
        for key in FIELDS:
            if key not in generated:
                generated[key] = np.nan if key in NUMERIC else None
        if 'exit_temp' in columns and 'temp_drop' in columns and 'rough_temp' in columns:
            generated['rough_temp'] = generated.exit_temp - generated.temp_drop
        generated['steel_grade'] = label
        generated['produced_at'] = (pd.Timestamp('2025-01-01') + pd.to_timedelta(rng.integers(0, 28 * 24 * 60, per_grade), unit='min')).strftime('%Y-%m-%dT%H:%M:%S')
        generated['furnace'] = None
        frames.append(generated)
        mapping.append({'source_grade': name, 'source_rank': rank + 1, 'public_grade': label})
    out = pd.concat(frames, ignore_index=True).iloc[rng.permutation(5 * per_grade)].reset_index(drop=True)
    out['slab_id'] = [f'DS-{i + 1:06d}' for i in range(len(out))]
    out['source_file'] = '脱敏合成演示.csv'
    out['source_sheet'] = '演示数据'
    out['source_row'] = np.arange(len(out)) + 2
    out['conversion_issue'] = False
    out['data_status'] = '脱敏合成演示；非真实生产记录'
    return quality_frame(out), mapping


def save_release(store: Store, d):
    """Save a source-derived draft only to a local private Store."""
    meta = store.save_dataset(d, '粗轧脱敏演示 · 五类钢种', 'sanitized', warnings=[NOTICE, POLICY['limitation']])
    meta['release'] = {**POLICY, 'records_per_grade': int(d.steel_grade.value_counts().iloc[0])}
    write_json(store.root / 'datasets' / meta['id'] / 'meta.json', meta)
    return meta
