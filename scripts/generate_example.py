import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.data import synthetic_dataframe

d = synthetic_dataframe()
d = d.drop(columns=['source_file', 'source_sheet', 'source_row', 'conversion_issue'])
d.to_csv(ROOT / 'data/examples/simulated_slabs.csv', index=False, encoding='utf-8-sig')
print('Generated 12,000 explicitly simulated records; random seed 1880.')

