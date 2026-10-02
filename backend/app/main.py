import json
import os
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .analysis import run_analysis
from .conditions import SnapshotIntegrityError, build_conditions
from .data import Store, apply_filters, synthetic_dataframe
from .privacy import ensure_public_dataset, is_independent_public_release
from .schema import AnalysisSpec, FIELDS, Filters, ImportSpec, Query

PROJECT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT / '.env')
MODE = os.environ.get('SLAB_MODE', 'public')
if MODE not in {'public', 'private'}:
    raise ValueError('SLAB_MODE 须为 public 或 private')
PUBLIC_MODE = MODE == 'public'
store = Store(os.environ.get('SLAB_DATA_DIR', PROJECT / ('runtime-public' if PUBLIC_MODE else 'runtime')))
if PUBLIC_MODE:
    ensure_public_dataset(store, PROJECT)
app = FastAPI(title='工业板坯数据工作台', version='1.0.0')

# GitHub Pages is served from a different origin than the Render API. Restrict
# browser access to explicitly configured origins; local development still uses
# Vite's same-origin proxy unless an origin is configured.
ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get('SLAB_ALLOWED_ORIGINS', '').split(',') if origin.strip()]
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type'],
        expose_headers=['Content-Disposition'],
    )

def allowed_dataset(ident):
    _, meta = store.get(ident)
    if meta.get('hidden') or (PUBLIC_MODE and not is_independent_public_release(meta)):
        raise HTTPException(404, '演示数据不存在')
    return meta

def allowed_analysis(ident):
    folder = store.root / 'analyses' / store.valid_id(ident)
    result = json.loads((folder / 'result.json').read_text())
    allowed_dataset(result['dataset_id'])
    return folder, result

def require_private():
    if PUBLIC_MODE:
        raise HTTPException(403, '公开演示模式不接收原始生产文件，请使用本地分析模式')

@app.exception_handler(ValueError)
async def invalid_request(request, exc):
    return JSONResponse(status_code=400, content={'detail': str(exc)})

@app.exception_handler(FileNotFoundError)
async def missing(request, exc):
    return JSONResponse(status_code=404, content={'detail': '数据或结果不存在，请重新选择'})

@app.get('/api/health')
def health():
    return {
        'status': 'ok',
        'version': '1.2.0',
        'ai': 'not_implemented',
        'mode': 'public_demo' if PUBLIC_MODE else 'private_local',
        'public_data': 'independent_simulation' if PUBLIC_MODE else None,
    }

@app.get('/api/schema')
def schema():
    return FIELDS

@app.get('/api/datasets')
def datasets():
    return [m for m in store.list_datasets() if not m.get('hidden') and (not PUBLIC_MODE or is_independent_public_release(m))]

@app.post('/api/datasets/demo')
def demo():
    if PUBLIC_MODE:
        return ensure_public_dataset(store, PROJECT)
    existing = next((d for d in store.list_datasets() if d['source_kind'] == 'simulated'), None)
    return existing or store.save_dataset(synthetic_dataframe(), '模拟板坯示例（12,000 条）', 'simulated', warnings=['固定随机种子 1880；人为设置变量关系；仅用于功能演示'])

@app.post('/api/uploads')
def upload(files: list[UploadFile] = File(...), header_row: int = Form(0)):
    require_private()
    if len(files) > 10 or not 0 <= header_row <= 30:
        raise ValueError('每次最多 10 个文件，表头行号须在 1—31 之间')
    results = []
    for file in files:
        content = file.file.read(100*1024*1024 + 1)
        if len(content) > 100*1024*1024:
            raise ValueError('单文件不能超过 100 MB')
        try:
            results.append(store.save_upload(file.filename or 'unnamed', content, header_row))
        except (ValueError, FileNotFoundError):
            raise
        except Exception as e:
            raise ValueError('文件无法解析，请检查文件格式、表头及是否加密') from e
    return results

@app.post('/api/datasets/import')
def import_data(spec: ImportSpec):
    require_private()
    return store.import_data(spec)

@app.get('/api/datasets/{ident}')
def metadata(ident: str):
    return allowed_dataset(ident)

@app.post('/api/datasets/{ident}/query')
def query(ident: str, req: Query):
    allowed_dataset(ident)
    return store.query(ident, req)

@app.post('/api/datasets/{ident}/records/{record_id}')
def record(ident: str, record_id: str, filters: Filters):
    allowed_dataset(ident)
    return store.record(ident, record_id, filters)

@app.post('/api/datasets/{ident}/export')
def export_scope(ident: str, filters: Filters):
    allowed_dataset(ident)
    d, _ = store.get(ident)
    selected = apply_filters(d, filters)
    content = selected.to_csv(index=False).encode('utf-8-sig')
    return Response(content=content, media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="filtered_records.csv"'})

@app.post('/api/datasets/{ident}/analyses')
def analyze(ident: str, spec: AnalysisSpec):
    allowed_dataset(ident)
    return run_analysis(store, ident, spec)

@app.get('/api/analyses')
def analyses(dataset_id: str | None = None):
    items = [json.loads(p.read_text()) for p in (store.root / 'analyses').glob('*/result.json')]
    visible = {m['id'] for m in datasets()}
    return sorted([i for i in items if i['dataset_id'] in visible and (not dataset_id or i['dataset_id'] == dataset_id)], key=lambda x: x['created_at'], reverse=True)

@app.post('/api/analyses/{ident}/rerun')
def rerun(ident: str):
    _, result = allowed_analysis(ident)
    return run_analysis(store, result['dataset_id'], AnalysisSpec(**result['parameters']))

@app.get('/api/analyses/{ident}/conditions')
def analysis_conditions(ident: str):
    folder, result = allowed_analysis(ident)
    try:
        return build_conditions(folder, result)
    except SnapshotIntegrityError as exc:
        raise HTTPException(409, str(exc)) from exc

@app.get('/api/analyses/{ident}/artifacts/{filename}')
def artifact(ident: str, filename: str, download: bool = False):
    folder, _ = allowed_analysis(ident)
    allowed = {'figure.png', 'figure.svg', 'figure.pdf', 'relationship.png', 'relationship.svg', 'relationship.pdf', 'relationships.csv', 'relationship_samples.csv', 'report.html', 'report.md', 'statistics.csv', 'samples.csv', 'parameters.json', 'result.json', 'bundle.zip'}
    if filename not in allowed:
        raise HTTPException(404, '文件不存在')
    path = folder / filename
    if not path.exists():
        raise HTTPException(404, '文件不存在')
    return FileResponse(path, filename=filename if download else None)

dist = PROJECT / 'frontend' / 'dist'
if dist.exists():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
