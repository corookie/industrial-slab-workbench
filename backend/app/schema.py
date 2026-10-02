from typing import Literal
from pydantic import BaseModel, Field

FIELDS = {
    'slab_id': {'label': '板坯编号', 'kind': 'text', 'unit': '', 'aliases': ['板坯编号', '板坯号', '板坯ID', 'slab_id']},
    'steel_grade': {'label': '钢种', 'kind': 'text', 'unit': '', 'aliases': ['钢种', '钢号', '出钢记号', 'steel_grade']},
    'produced_at': {'label': '出钢 / 生产时间', 'kind': 'date', 'unit': '', 'aliases': ['生产时间', '出钢时间', 'produced_at']},
    'length': {'label': '板坯长度', 'kind': 'number', 'unit': 'mm', 'aliases': ['长度', '板坯长度', 'length']},
    'width': {'label': '板坯宽度', 'kind': 'number', 'unit': 'mm', 'aliases': ['宽度', '板坯宽度', 'width']},
    'thickness': {'label': '板坯厚度', 'kind': 'number', 'unit': 'mm', 'aliases': ['厚度', '板坯厚度', 'thickness']},
    'rough_thickness': {'label': '粗轧厚度', 'kind': 'number', 'unit': 'mm', 'aliases': ['粗轧厚度', 'rough_thickness']},
    'rolling_thickness': {'label': '轧制厚度', 'kind': 'number', 'unit': 'mm', 'aliases': ['轧制厚度', '精轧厚度', 'rolling_thickness']},
    'exit_temp': {'label': '出炉温度', 'kind': 'number', 'unit': '°C', 'aliases': ['出炉温度', '出钢温度', 'exit_temp']},
    'charge_temp': {'label': '装钢温度', 'kind': 'number', 'unit': '°C', 'aliases': ['装钢温度', 'charge_temp']},
    'rough_temp': {'label': '粗轧温度', 'kind': 'number', 'unit': '°C', 'aliases': ['粗轧温度', 'rough_temp']},
    'finish_temp': {'label': '精轧温度', 'kind': 'number', 'unit': '°C', 'aliases': ['精轧温度', 'finish_temp']},
    'temp_drop': {'label': '粗轧温降', 'kind': 'number', 'unit': '°C', 'aliases': ['粗轧温降', '温降', 'temp_drop']},
    'process_time': {'label': '粗轧过程时间', 'kind': 'number', 'unit': 's', 'aliases': ['粗轧过程时间', '过程时间', 'process_time']},
    'furnace_time': {'label': '在炉时间', 'kind': 'number', 'unit': 'min', 'aliases': ['在炉时间', 'furnace_time']},
    'weight': {'label': '重量', 'kind': 'number', 'unit': 'kg', 'aliases': ['重量', 'weight']},
    'furnace': {'label': '炉号', 'kind': 'text', 'unit': '', 'aliases': ['炉号', 'furnace']},
}
NUMERIC = [k for k, v in FIELDS.items() if v['kind'] == 'number']
VARIABLES = ['rough_thickness', 'process_time', 'exit_temp', 'furnace_time', 'width', 'thickness', 'rolling_thickness', 'charge_temp', 'length', 'weight']

class Filters(BaseModel):
    grades: list[str] = Field(default_factory=list)
    ranges: dict[str, list[float | None]] = Field(default_factory=dict)
    date_start: str | None = None
    date_end: str | None = None
    exclude_invalid: bool = True

class Query(BaseModel):
    filters: Filters = Field(default_factory=Filters)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=200)
    x_field: Literal['rough_thickness', 'thickness', 'rolling_thickness', 'exit_temp', 'process_time'] = 'rough_thickness'
    selected_id: str | None = None
    locate_selected: bool = False

class TableSpec(BaseModel):
    upload_id: str
    sheet: str
    header_row: int = Field(default=0, ge=0, le=30)
    role: Literal['main', 'append', 'join'] = 'main'
    mapping: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)

class ImportSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_kind: Literal['real', 'simulated'] = 'real'
    units_confirmed: bool
    tables: list[TableSpec] = Field(min_length=1, max_length=30)

class AnalysisSpec(BaseModel):
    filters: Filters = Field(default_factory=Filters)
    steel_grade: str = Field(min_length=1)
    controls: dict[str, list[float | None]] = Field(default_factory=dict)
    variable: Literal['rough_thickness', 'process_time', 'exit_temp', 'furnace_time', 'width', 'thickness', 'rolling_thickness', 'charge_temp', 'length', 'weight'] = 'rough_thickness'
    bins: list[float] = Field(min_length=3, max_length=21)
    error_bar: Literal['sd', 'ci95'] = 'sd'

    relationship_fields: list[Literal['rough_thickness', 'process_time', 'exit_temp', 'furnace_time', 'width', 'thickness', 'rolling_thickness', 'charge_temp', 'length', 'weight']] | None = Field(default=None, max_length=10)
    effect_step: float | None = Field(default=None, gt=0, le=100000, allow_inf_nan=False)
