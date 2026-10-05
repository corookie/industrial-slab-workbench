"""Stdlib release gate: static analysis must match the bundled data and code."""
import ast
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from build_quick_demo import build_payload

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'frontend/src/data/quick-analysis.json'
ASSETS = ROOT / 'frontend/public/quick-analysis'


def check_bundle():
    saved = json.loads(BUNDLE.read_text(encoding='utf-8'))
    result = saved['result']
    dataset = build_payload()['meta']
    if (result.get('quick_dataset_sha256') != dataset['sha256']
            or result.get('dataset_id') != dataset['id'] or not result.get('precomputed')
            or result.get('source_kind') != 'simulated'
            or result.get('release', {}).get('data_origin') != 'independent_simulation'):
        raise ValueError('内置分析与独立模拟数据不一致，请重新生成')
    code_sha = hashlib.sha256(b''.join((ROOT / 'backend/app' / name).read_bytes()
                    for name in ['analysis.py', 'relationships.py', 'data.py', 'schema.py', 'privacy.py'])).hexdigest()
    if result['code_sha256'] != code_sha:
        raise ValueError('分析实现已改变，请重新生成内置分析')
    tree = ast.parse((ROOT / 'scripts/build_quick_analysis.py').read_text(encoding='utf-8'))
    parameters = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'DEFAULT_PARAMETERS' for t in node.targets))
    if parameters != result['parameters']:
        raise ValueError('默认分析参数已改变，请重新生成内置分析')
    if saved['conditions']['samples_sha256'] != result['samples_sha256']:
        raise ValueError('三维数据与分析样本指纹不一致')
    if result['counts']['source'] != 1000 or result['counts']['analyzed'] != sum(group['n'] for group in result['groups']):
        raise ValueError('内置分析样本计数不一致')
    actual_files = {file.name for file in ASSETS.iterdir() if file.is_file()}
    if actual_files != set(saved['files_sha256']):
        raise ValueError('内置分析图件和报告不完整')
    for name, sha in saved['files_sha256'].items():
        if hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() != sha:
            raise ValueError(f'内置分析文件校验失败：{name}')
    if json.loads((ASSETS / 'result.json').read_text(encoding='utf-8')) != result:
        raise ValueError('下载结果与页面结果不一致')
    if hashlib.sha256((ASSETS / 'dataset.csv').read_bytes()).hexdigest() != result['dataset_sha256']:
        raise ValueError('复现输入数据指纹不一致')
    if hashlib.sha256((ASSETS / 'samples.csv').read_bytes()).hexdigest() != result['samples_sha256']:
        raise ValueError('分析样本快照指纹不一致')
    with (ASSETS / 'dataset.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    quick = build_payload()
    expected = [dict(zip(quick['columns'], values)) for values in quick['rows']]
    if len(rows) != len(expected):
        raise ValueError('复现输入不是 1,000 条内置数据')
    for actual, reference in zip(rows, expected):
        if actual['record_id'] != f'quick-{reference["backend_row_index"]}':
            raise ValueError('内置分析记录标识与工作台不一致')
        for key, value in reference.items():
            if key == 'backend_row_index':
                continue
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                matches = float(actual[key]) == value
            else:
                matches = actual[key] == ('' if value is None else str(value))
            if not matches:
                raise ValueError('内置分析输入数值与网页示例不一致')
    with zipfile.ZipFile(ASSETS / 'bundle.zip') as archive:
        if set(archive.namelist()) != set(saved['files_sha256']) - {'bundle.zip'}:
            raise ValueError('实验包内容不完整')
        for name in archive.namelist():
            if hashlib.sha256(archive.read(name)).hexdigest() != saved['files_sha256'][name]:
                raise ValueError('实验包与独立下载文件不一致')
    return saved


if __name__ == '__main__':
    payload = check_bundle()
    print(f'Precomputed analysis ready: {payload["result"]["counts"]["analyzed"]} records from the 1,000-row demo')
