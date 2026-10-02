import hashlib
import json
import re
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import FIELDS, NUMERIC, Filters, ImportSpec, Query, TableSpec

def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    return value

def write_json(path, data):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(json_safe(data), ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def fingerprint(data):
    return hashlib.sha256(json.dumps(json_safe(data), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def read_table(path: Path, sheet: str = '', header_row=0):
    if path.suffix.lower() == '.csv':
        last = None
        for encoding in ['utf-8-sig', 'gb18030']:
            try:
                d = pd.read_csv(path, encoding=encoding, header=header_row, dtype=object)
                break
            except UnicodeDecodeError as e:
                last = e
        else:
            raise ValueError('CSV 编码无法识别，请保存为 UTF-8') from last
    else:
        d = pd.read_excel(path, sheet_name=sheet, header=header_row, dtype=object)
    if len(d) > 500_000:
        raise ValueError('首版单表最多支持 50 万行')
    d.columns = [str(c).strip() for c in d.columns]
    d = d.dropna(how='all')
    return d

def infer_mapping(columns):
    norm = lambda s: re.sub(r'[\s（）()_]', '', s).lower()
    result = {}
    for key, field in FIELDS.items():
        match = next((c for c in columns if norm(c) in {norm(a) for a in field['aliases']}), None)
        if match is not None:
            result[key] = match
    return result

def preview_table(d, name):
    mapping = infer_mapping(d.columns)
    cols = []
    for c in d.columns:
        values = d[c].mask(d[c].map(lambda v: isinstance(v, str) and not v.strip()))
        numeric = pd.to_numeric(values, errors='coerce')
        cols.append({'name': c, 'missing': int(values.isna().sum()), 'unique': int(values.nunique()),
                     'numeric_count': int(numeric.notna().sum()), 'min': numeric.min(), 'max': numeric.max()})
    return json_safe({'sheet': name, 'rows': len(d), 'columns': cols,
                     'preview': d.head(5).where(d.head(5).notna(), None).to_dict('records'),
                     'mapping': mapping, 'units': {k: FIELDS[k]['unit'] for k in mapping if k in NUMERIC}})

def normalized(d: pd.DataFrame, spec: TableSpec, file_name: str):
    unknown = set(spec.mapping) - set(FIELDS)
    if unknown:
        raise ValueError('不支持的映射字段：' + ', '.join(unknown))
    mapped = [v for v in spec.mapping.values() if v]
    if len(mapped) != len(set(mapped)):
        raise ValueError('同一个原始字段不能同时映射到多个指标')
    out = pd.DataFrame(index=d.index)
    warnings = []
    bad_conversion = pd.Series(False, index=d.index)
    for key, field in FIELDS.items():
        col = spec.mapping.get(key)
        if not col:
            out[key] = np.nan if key in NUMERIC else None
            continue
        if col not in d:
            raise ValueError(f'字段不存在：{col}')
        values = d[col].mask(d[col].map(lambda v: isinstance(v, str) and not v.strip()))
        if key in NUMERIC:
            unit = spec.units.get(key)
            permitted = {'mm': ['mm', 'cm', 'm'], '°C': ['°C', 'K'], 's': ['s', 'min'],
                         'min': ['min', 's'], 'kg': ['kg', 't']}[field['unit']]
            if unit not in permitted:
                raise ValueError(f'{field["label"]}需要确认单位，可选：{", ".join(permitted)}')
            v = pd.to_numeric(values, errors='coerce').astype(float)
            errors = values.notna() & (v.isna() | ~np.isfinite(v))
            bad_conversion |= errors
            v = v.where(np.isfinite(v))
            if errors.any():
                warnings.append(f'{col} 有 {int(errors.sum())} 个无法转换的数值，已记为缺失并标记异常')
            if field['unit'] == 'mm':
                v *= {'mm': 1, 'cm': 10, 'm': 1000}[unit]
            elif field['unit'] == '°C' and unit == 'K':
                # Temperature difference in Kelvin has the same magnitude as in Celsius.
                if key != 'temp_drop':
                    v -= 273.15
            elif field['unit'] == 's' and unit == 'min':
                v *= 60
            elif field['unit'] == 'min' and unit == 's':
                v /= 60
            elif unit == 't':
                v *= 1000
            out[key] = v
        elif field['kind'] == 'date':
            numeric_dates = values.map(lambda x: isinstance(x, (int, float)) and pd.notna(x))
            if numeric_dates.any():
                raise ValueError('生产时间含 Excel 数字日期，请先在源文件转为日期或文本日期，避免猜测时间口径')
            parsed = pd.to_datetime(values, errors='coerce', format='mixed')
            errors = values.notna() & parsed.isna()
            if errors.any():
                warnings.append(f'{col} 有 {int(errors.sum())} 个无法识别的日期，已记为缺失')
            out[key] = parsed.dt.strftime('%Y-%m-%dT%H:%M:%S').where(parsed.notna(), None)
        else:
            out[key] = values.map(lambda v: str(v).strip() if pd.notna(v) else None)
    out['source_file'] = file_name
    out['source_sheet'] = spec.sheet
    out['source_row'] = d.index + spec.header_row + 2
    out['conversion_issue'] = bad_conversion
    return out, warnings

def quality_frame(d):
    flags = pd.Series('', index=d.index)
    invalid = d['conversion_issue'].fillna(False).astype(bool)
    flags = flags.mask(invalid, '数值转换失败；')
    for key in ['length', 'width', 'thickness', 'rough_thickness', 'rolling_thickness',
                'exit_temp', 'rough_temp', 'finish_temp', 'process_time', 'furnace_time', 'weight']:
        mask = d[key].notna() & (d[key] <= 0)
        invalid |= mask
        flags = flags + mask.map({True: FIELDS[key]['label'] + '≤0；', False: ''})
    mask = d['temp_drop'].notna() & (d['temp_drop'] < 0)
    invalid |= mask
    flags = flags + mask.map({True: '温降<0；', False: ''})
    d['invalid'] = invalid
    d['quality_note'] = flags.str.rstrip('；')
    return d

def apply_filters(d, filters: Filters):
    mask = pd.Series(True, index=d.index)
    if filters.exclude_invalid:
        mask &= ~d['invalid']
    if filters.grades:
        mask &= d['steel_grade'].isin(filters.grades)
    for key, bounds in filters.ranges.items():
        if key not in NUMERIC or len(bounds) != 2:
            raise ValueError('筛选区间必须是支持的数值字段及两个边界')
        lo, hi = bounds
        if any(x is not None and not np.isfinite(x) for x in bounds):
            raise ValueError('筛选边界必须是有限数值')
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f'{FIELDS[key]["label"]}下限不能大于上限')
        if lo is not None:
            mask &= d[key] >= lo
        if hi is not None:
            mask &= d[key] <= hi
    times = pd.to_datetime(d['produced_at'], errors='coerce')
    for bound, is_end in [(filters.date_start, False), (filters.date_end, True)]:
        if bound:
            try:
                ts = pd.Timestamp(bound)
            except Exception as e:
                raise ValueError('无法识别筛选日期') from e
            if is_end and len(bound) == 10:
                mask &= times < ts + pd.Timedelta(days=1)
            else:
                mask &= (times <= ts) if is_end else (times >= ts)
    if filters.date_start and filters.date_end and pd.Timestamp(filters.date_start) > pd.Timestamp(filters.date_end):
        raise ValueError('起始日期不能晚于结束日期')
    return d.loc[mask]

class Store:
    def __init__(self, root):
        self.root = Path(root)
        for folder in ['uploads', 'datasets', 'analyses']:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.cache = OrderedDict()

    def valid_id(self, ident):
        if not re.fullmatch(r'[a-f0-9]{32}', ident):
            raise ValueError('无效的数据标识')
        return ident

    def upload_path(self, ident):
        folder = self.root / 'uploads' / self.valid_id(ident)
        info = json.loads((folder / 'meta.json').read_text())
        return folder / info['stored_name'], info

    def save_upload(self, filename, content, header_row=0):
        suffix = Path(filename).suffix.lower()
        if suffix not in ['.xlsx', '.csv']:
            raise ValueError('请上传 .xlsx 或 .csv 文件；旧版 .xls 请另存为 .xlsx')
        ident = uuid.uuid4().hex
        folder = self.root / 'uploads' / ident
        folder.mkdir()
        path = folder / ('source' + suffix)
        path.write_bytes(content)
        info = {'id': ident, 'filename': Path(filename).name, 'stored_name': path.name,
                'sha256': hashlib.sha256(content).hexdigest(), 'header_row': header_row}
        write_json(folder / 'meta.json', info)
        sheets = ['CSV'] if suffix == '.csv' else pd.ExcelFile(path).sheet_names
        if len(sheets) > 40:
            raise ValueError('首版支持每个文件最多 40 个工作表')
        return {**info, 'tables': [preview_table(read_table(path, s, header_row), s) for s in sheets]}

    def import_data(self, spec: ImportSpec):
        if not spec.units_confirmed:
            raise ValueError('请先确认字段含义和单位')
        if sum(t.role == 'main' for t in spec.tables) != 1:
            raise ValueError('请选择且仅选择一个主表')
        prepared, warnings, provenance = [], [], []
        for table in spec.tables:
            if not any(table.mapping.values()):
                raise ValueError('每个参与导入的表至少需要映射一个字段')
            path, info = self.upload_path(table.upload_id)
            d, ws = normalized(read_table(path, table.sheet, table.header_row), table, info['filename'])
            prepared.append((table.role, d))
            warnings += ws
            provenance.append({**table.model_dump(), 'file': info['filename'], 'sha256': info['sha256'], 'rows': len(d)})
        primary = next(d for role, d in prepared if role == 'main')
        appended = [d for role, d in prepared if role == 'append']
        primary = pd.concat([primary] + appended, ignore_index=True)
        count_before = len(primary)
        join_info = []
        for role, other in prepared:
            if role != 'join':
                continue
            if primary['slab_id'].isna().any() or other['slab_id'].isna().any():
                raise ValueError('按编号关联要求主表和关联表的板坯编号均完整；当前文件没有编号时请使用独立数据集或按行追加')
            if other['slab_id'].duplicated().any():
                raise ValueError('关联表板坯编号重复，已阻止关联以避免样本膨胀；请先明确每块板坯的记录口径')
            merged = primary.merge(other, on='slab_id', how='left', suffixes=('', '__right'), validate='many_to_one', indicator=True)
            matched = int((merged['_merge'] == 'both').sum())
            conflicts = {}
            for key in FIELDS:
                if key == 'slab_id':
                    continue
                right = key + '__right'
                both = merged[key].notna() & merged[right].notna()
                conflict = both & (merged[key].astype(str) != merged[right].astype(str))
                if conflict.any():
                    conflicts[key] = int(conflict.sum())
                merged[key] = merged[key].combine_first(merged[right])
            merged['conversion_issue'] = merged['conversion_issue'] | merged['conversion_issue__right'].fillna(False)
            primary = merged[primary.columns].copy()
            join_info.append({'matched': matched, 'unmatched': len(merged) - matched, 'conflicts': conflicts,
                              'policy': '左关联；仅填充主表缺失值；冲突保留主表；many_to_one 验证'})
            if conflicts:
                warnings.append('关联字段存在冲突，已保留主表值，详细计数见数据来源记录')
        if len(primary) != count_before:
            raise ValueError('关联后行数发生变化，已阻止导入')
        if len(primary) == 0:
            raise ValueError('数据表为空')
        if len(primary) > 500_000:
            raise ValueError('首版数据集最多 50 万行')
        return self.save_dataset(primary, spec.name, spec.source_kind, provenance, warnings, join_info)

    def save_dataset(self, d, name, kind, provenance=None, warnings=None, joins=None):
        ident = uuid.uuid4().hex
        d = d.reset_index(drop=True)
        d['record_id'] = [f'{ident[:10]}-{i+1:07d}' for i in range(len(d))]
        d['steel_grade'] = d['steel_grade'].fillna('未提供钢种')
        d = quality_frame(d)
        available = [k for k in FIELDS if d[k].notna().any()]
        quality = {'invalid_rows': int(d['invalid'].sum()),
                   'missing': {k: int(d[k].isna().sum()) for k in FIELDS},
                   'duplicate_slab_ids': int(d['slab_id'].dropna().duplicated().sum()),
                   'id_policy': '提供板坯编号时保留；每条记录另有稳定记录标识；缺少编号时不自动关联'}
        folder = self.root / 'datasets' / ident
        folder.mkdir()
        d.to_csv(folder / 'normalized.csv', index=False, encoding='utf-8-sig')
        sha = hashlib.sha256((folder / 'normalized.csv').read_bytes()).hexdigest()
        meta = {'id': ident, 'name': name, 'source_kind': kind, 'rows': len(d), 'available': available,
                'created_at': datetime.now(timezone.utc).isoformat(), 'quality': quality,
                'bounds': {k: {'min': d[k].min(), 'max': d[k].max()} for k in NUMERIC if k in available},
                'grades': [{'name': str(k), 'count': int(v)} for k, v in d['steel_grade'].value_counts().items()],
                'provenance': provenance or [], 'warnings': warnings or [], 'joins': joins or [], 'sha256': sha,
                'units': {k: FIELDS[k]['unit'] for k in available}}
        write_json(folder / 'meta.json', meta)
        self._cache(ident, d)
        return json_safe(meta)

    def _cache(self, ident, d):
        self.cache[ident] = d
        self.cache.move_to_end(ident)
        while len(self.cache) > 5:
            self.cache.popitem(last=False)

    def get(self, ident):
        folder = self.root / 'datasets' / self.valid_id(ident)
        meta = json.loads((folder / 'meta.json').read_text())
        if ident not in self.cache:
            d = pd.read_csv(folder / 'normalized.csv', dtype={k: str for k in ['record_id', 'slab_id', 'steel_grade', 'furnace', 'produced_at']})
            for k in NUMERIC:
                d[k] = pd.to_numeric(d[k], errors='coerce')
            self._cache(ident, d)
        return self.cache[ident], meta

    def list_datasets(self):
        files = (self.root / 'datasets').glob('*/meta.json')
        return sorted([json.loads(f.read_text()) for f in files], key=lambda d: d['created_at'], reverse=True)

    def query(self, ident, req: Query):
        original, meta = self.get(ident)
        d = apply_filters(original, req.filters)
        histograms = {}
        for key in ['thickness', 'rough_thickness', 'rolling_thickness', 'exit_temp', 'temp_drop']:
            values = d[key].dropna()
            if len(values):
                counts, edges = np.histogram(values, bins=min(16, max(1, values.nunique())))
                histograms[key] = {'counts': counts.tolist(), 'edges': edges.tolist(), 'valid_n': len(values), 'missing_n': int(d[key].isna().sum())}
        scatter = d.dropna(subset=[req.x_field, 'temp_drop'])
        if len(scatter) > 2500:
            scatter = scatter.iloc[np.linspace(0, len(scatter)-1, 2500, dtype=int)]
        points = scatter[[req.x_field, 'temp_drop', 'record_id', 'steel_grade']].values.tolist()
        page = min(req.page, max(1, int(np.ceil(len(d) / req.page_size))))
        if req.locate_selected and req.selected_id:
            found = np.flatnonzero(d['record_id'].to_numpy() == req.selected_id)
            if len(found):
                page = int(found[0] // req.page_size + 1)
        records = d.iloc[(page-1)*req.page_size:page*req.page_size].to_dict('records')
        selected = d[d['record_id'] == req.selected_id] if req.selected_id else d.iloc[:1]
        if selected.empty:
            selected = d.iloc[:1]
        scales = {k: {'min': d[k].min(), 'max': d[k].max()} for k in ['exit_temp', 'temp_drop'] if d[k].notna().any()}
        scope = fingerprint({'dataset_sha256': meta['sha256'], 'filters': req.filters.model_dump()})
        return json_safe({'dataset_id': ident, 'scope': scope, 'filters': req.filters.model_dump(),
                          'total': len(d), 'source_total': len(original), 'invalid_in_scope': int(d['invalid'].sum()),
                          'invalid_in_dataset': meta['quality']['invalid_rows'], 'grades': [{'name': k, 'value': int(v)} for k, v in d['steel_grade'].value_counts().items()],
                          'histograms': histograms, 'scatter': points, 'scatter_valid_n': int(d[[req.x_field, 'temp_drop']].dropna().shape[0]),
                          'records': records, 'page': page, 'page_size': req.page_size,
                          'selected': selected.iloc[0].to_dict() if len(selected) else None, 'color_scales': scales})

    def record(self, ident, record_id, filters):
        d, _ = self.get(ident)
        selected = apply_filters(d, filters)
        row = selected[selected['record_id'] == record_id]
        if row.empty:
            raise ValueError('该记录不在当前筛选范围，请刷新数据')
        return json_safe(row.iloc[0].to_dict())

def synthetic_dataframe(n=12000):
    rng = np.random.default_rng(1880)
    grades = rng.choice(['DEMO-A', 'DEMO-B', 'DEMO-C'], n, p=[.5, .3, .2])
    rough = rng.uniform(32, 49, n)
    exit_t = rng.normal(1200, 17, n)
    process = rng.normal(210, 18, n)
    loss = 148 + .18*(exit_t-1200) + .14*(process-210) - .65*(rough-40) + (grades == 'DEMO-B')*7 + rng.normal(0, 8, n)
    d = pd.DataFrame({'slab_id': [f'DEMO-{i+1:06d}' for i in range(n)], 'steel_grade': grades,
                      'produced_at': pd.date_range('2023-02-01', periods=n, freq='150s').strftime('%Y-%m-%dT%H:%M:%S'),
                      'length': rng.uniform(8500, 11000, n).round(0), 'width': rng.choice([1100, 1250, 1450, 1600], n),
                      'thickness': rng.choice([210, 230, 250], n), 'rough_thickness': rough.round(3),
                      'rolling_thickness': rng.uniform(2, 6, n).round(3), 'exit_temp': exit_t.round(2),
                      'temp_drop': loss.round(2), 'process_time': process.round(2), 'furnace_time': rng.normal(195, 20, n).round(2),
                      'charge_temp': rng.uniform(100, 600, n).round(0), 'weight': rng.uniform(20000, 27000, n).round(0),
                      'rough_temp': (exit_t-loss).round(2), 'finish_temp': rng.normal(900, 15, n).round(2), 'furnace': rng.choice(['2', '3', '4'], n),
                      'source_file': '模拟示例.csv', 'source_sheet': 'CSV', 'source_row': np.arange(n)+2, 'conversion_issue': False})
    d.loc[0, 'length'] = np.nan
    d.loc[1, 'temp_drop'] = -10
    d.loc[2, 'exit_temp'] = 0
    return d
