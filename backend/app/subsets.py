"""Local, unmodified production-data subsets. Never a public release."""
from .data import Store, write_json
from .privacy import top_grade_names


def create_original_top_five(store: Store, source_id: str):
    original, source = store.get(source_id)
    if source['source_kind'] != 'real' or source.get('selection'):
        raise ValueError('请选择完整的真实源数据集')
    ranked = top_grade_names(original)
    existing = next((m for m in store.list_datasets()
                     if m.get('selection', {}).get('source_dataset_id') == source_id
                     and m.get('selection', {}).get('source_sha256') == source['sha256']
                     and m.get('selection', {}).get('kind') == 'top_five_original'), None)
    if existing:
        return existing
    selected = original.loc[original.steel_grade.isin(ranked)].copy()
    selected['source_record_id'] = selected['record_id']
    meta = store.save_dataset(selected, '原始粗轧记录 · 数量前五钢种（仅本地）', 'real',
                              provenance=source['provenance'],
                              warnings=[*source['warnings'], '真实生产数据，仅供本地分析；仅取原始记录数量最多的五个钢种，数值、时间及来源保留原样。'])
    meta['selection'] = {'kind': 'top_five_original', 'count': 5,
                         'ranking': '原始全部非空钢种记录数量；并列按文本排序；排名在排除异常及交互筛选前确定',
                         'source_dataset_id': source_id, 'source_sha256': source['sha256'],
                         'source_rows': len(original), 'selected_rows': len(selected), 'grades': ranked}
    write_json(store.root / 'datasets' / meta['id'] / 'meta.json', meta)
    return meta


def hide_dataset(store: Store, ident: str):
    _, meta = store.get(ident)
    meta['hidden'] = True
    write_json(store.root / 'datasets' / ident / 'meta.json', meta)
