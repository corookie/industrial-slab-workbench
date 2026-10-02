"""Read-only three-axis condition data derived from an analysis snapshot."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


AXES = ('exit_temp', 'process_time', 'rough_thickness')
COLOR_FIELD = 'temp_drop'
REQUIRED_NUMERIC_FIELDS = (*AXES, COLOR_FIELD)
POINT_LIMIT = 5_000


class SnapshotIntegrityError(ValueError):
    """The saved analysis snapshot can no longer be used reproducibly."""


def _empty_bounds() -> dict[str, dict[str, None]]:
    return {field: {'min': None, 'max': None} for field in AXES}


def _empty_color_scale() -> dict[str, None]:
    return {'min': None, 'max': None}


def _read_snapshot(folder: Path, result: Mapping[str, Any]) -> tuple[pd.DataFrame, int, str]:
    """Load a snapshot only after checking the metadata that identifies it."""
    analysis_id = folder.name
    if result.get('id') != analysis_id:
        raise SnapshotIntegrityError('分析快照标识不一致，请重新运行分析')

    counts = result.get('counts')
    analyzed = counts.get('analyzed') if isinstance(counts, Mapping) else None
    if isinstance(analyzed, bool) or not isinstance(analyzed, int) or analyzed < 0:
        raise SnapshotIntegrityError('分析结果缺少有效的样本数量，请重新运行分析')

    expected_hash = result.get('samples_sha256')
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise SnapshotIntegrityError('分析结果缺少有效的样本快照指纹，请重新运行分析')

    path = folder / 'samples.csv'
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise SnapshotIntegrityError('分析样本快照不可读取，请重新运行分析') from exc

    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != expected_hash:
        raise SnapshotIntegrityError('分析样本快照校验失败，请重新运行分析')

    try:
        frame = pd.read_csv(
            io.BytesIO(content),
            encoding='utf-8-sig',
            # These are identifiers/labels, not measurements.  In particular,
            # a numeric-looking slab number can have meaningful leading zeroes.
            dtype={'record_id': 'string', 'slab_id': 'string', 'steel_grade': 'string', 'produced_at': 'string'},
            # Keep a literal label such as "NA" intact; blank values are
            # normalized to null below instead of becoming an identity string.
            keep_default_na=False,
        )
    except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise SnapshotIntegrityError('分析样本快照无法读取，请重新运行分析') from exc

    if len(frame) != analyzed:
        raise SnapshotIntegrityError('分析样本快照数量与分析结果不一致，请重新运行分析')
    return frame, analyzed, expected_hash


def _nullable_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values without ever emitting non-finite JSON."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _snapshot_conditions(result: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    dataset_id = result.get('dataset_id')
    source_kind = result.get('source_kind')
    if not isinstance(dataset_id, str) or not dataset_id:
        raise SnapshotIntegrityError('分析结果缺少数据集标识，请重新运行分析')
    if not isinstance(source_kind, str) or not source_kind:
        raise SnapshotIntegrityError('分析结果缺少数据来源类型，请重新运行分析')

    raw_conditions = result.get('conditions', [])
    if isinstance(raw_conditions, str):
        raw_conditions = [raw_conditions]
    if not isinstance(raw_conditions, list):
        raw_conditions = []
    return dataset_id, source_kind, [item for item in raw_conditions if isinstance(item, str)]


def _points(frame: pd.DataFrame, numeric: dict[str, np.ndarray], positions: np.ndarray) -> list[dict[str, Any]]:
    points = []
    for position in positions:
        row = frame.iloc[int(position)]
        points.append({
            'record_id': _nullable_value(row.get('record_id')),
            'slab_id': _nullable_value(row.get('slab_id')),
            'source_row': _nullable_value(row.get('source_row')),
            'steel_grade': _nullable_value(row.get('steel_grade')),
            'exit_temp': float(numeric['exit_temp'][position]),
            'process_time': float(numeric['process_time'][position]),
            'rough_thickness': float(numeric['rough_thickness'][position]),
            'temp_drop': float(numeric['temp_drop'][position]),
            'group_index': _nullable_value(row.get('group_index')),
            'produced_at': _nullable_value(row.get('produced_at')),
        })
    return points


def build_conditions(folder: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a bounded three-axis view from one immutable ``samples.csv`` snapshot.

    The returned ranges always use every valid saved sample.  Rendering is the
    only bounded operation, and it preserves snapshot record order.
    """
    frame, analyzed, samples_sha256 = _read_snapshot(folder, result)
    dataset_id, source_kind, conditions = _snapshot_conditions(result)
    payload: dict[str, Any] = {
        'analysis_id': folder.name,
        'dataset_id': dataset_id,
        'samples_sha256': samples_sha256,
        'counts': {'analyzed': analyzed, 'eligible': 0, 'missing_coordinates': analyzed, 'rendered': 0},
        'points': [],
        'bounds': _empty_bounds(),
        'color_scale': _empty_color_scale(),
        'conditions': conditions,
        'sampling': 'none',
        'source_kind': source_kind,
        'warnings': [],
    }

    missing_fields = [field for field in REQUIRED_NUMERIC_FIELDS if field not in frame.columns]
    if missing_fields:
        payload['warnings'].append('分析快照缺少三维工况字段：' + '、'.join(missing_fields))
        return payload

    numeric = {
        field: pd.to_numeric(frame[field], errors='coerce').to_numpy(dtype='float64', na_value=np.nan)
        for field in REQUIRED_NUMERIC_FIELDS
    }
    finite = np.logical_and.reduce([np.isfinite(numeric[field]) for field in REQUIRED_NUMERIC_FIELDS])
    eligible_positions = np.flatnonzero(finite)
    eligible = int(len(eligible_positions))
    payload['counts'] = {
        'analyzed': analyzed,
        'eligible': eligible,
        'missing_coordinates': analyzed - eligible,
        'rendered': min(eligible, POINT_LIMIT),
    }
    if not eligible:
        payload['warnings'].append('分析快照中没有同时具备三轴坐标和温降的有限数值记录')
        return payload

    payload['bounds'] = {
        field: {
            'min': float(numeric[field][finite].min()),
            'max': float(numeric[field][finite].max()),
        }
        for field in AXES
    }
    payload['color_scale'] = {
        'min': float(numeric[COLOR_FIELD][finite].min()),
        'max': float(numeric[COLOR_FIELD][finite].max()),
    }

    if eligible > POINT_LIMIT:
        indices = np.array([(index * (eligible - 1)) // (POINT_LIMIT - 1) for index in range(POINT_LIMIT)], dtype=int)
        rendered_positions = eligible_positions[indices]
        payload['sampling'] = 'deterministic_record_order'
    else:
        rendered_positions = eligible_positions
    payload['points'] = _points(frame, numeric, rendered_positions)
    return payload
