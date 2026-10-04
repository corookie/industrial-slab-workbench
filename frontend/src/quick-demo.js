import bundle from './data/quick-demo.json' with { type: 'json' }

export const quickSchema = bundle.schema
export const quickDataset = bundle.meta
const numeric = Object.keys(quickSchema).filter(key => quickSchema[key].kind === 'number')
const records = bundle.rows.map(values => {
  const row = Object.fromEntries(bundle.columns.map((key, index) => [key, values[index]]))
  return {...row, record_id: `quick-${row.backend_row_index}`}
})
const present = value => value !== null && value !== undefined && Number.isFinite(value)

export function quickRows(filters = {}) {
  for (const [key, bounds] of Object.entries(filters.ranges || {})) {
    if (!numeric.includes(key) || bounds.length !== 2 || bounds.some(v => v !== null && !Number.isFinite(v)))
      throw new Error('筛选区间必须是支持的数值字段及两个有限边界')
    if (bounds[0] !== null && bounds[1] !== null && bounds[0] > bounds[1])
      throw new Error(`${quickSchema[key].label}下限不能大于上限`)
  }
  if (filters.date_start && filters.date_end && filters.date_start > filters.date_end)
    throw new Error('起始日期不能晚于结束日期')
  return records.filter(row => {
    if (filters.exclude_invalid !== false && row.invalid) return false
    if (filters.grades?.length && !filters.grades.includes(row.steel_grade)) return false
    for (const [key, [lo, hi]] of Object.entries(filters.ranges || {})) {
      if ((lo !== null || hi !== null) && (!present(row[key]) || lo !== null && row[key] < lo || hi !== null && row[key] > hi)) return false
    }
    const date = row.produced_at?.slice(0, 10)
    if (filters.date_start && (!date || date < filters.date_start)) return false
    if (filters.date_end && (!date || date > filters.date_end)) return false
    return true
  })
}

function histogram(values, missing) {
  let min = Math.min(...values), max = Math.max(...values)
  const bins = Math.min(16, new Set(values).size)
  if (min === max) { min -= .5; max += .5 }
  const edges = Array.from({length: bins + 1}, (_, i) => min + (max - min) * i / bins)
  const counts = Array(bins).fill(0)
  for (const value of values) counts[Math.min(bins - 1, Math.floor((value - min) / (max - min) * bins))]++
  return {counts, edges, valid_n: values.length, missing_n: missing}
}

export function quickQuery(request = {}) {
  const filters = {grades: [], ranges: {}, date_start: null, date_end: null, exclude_invalid: true, ...request.filters}
  const rows = quickRows(filters)
  const histograms = {}, scales = {}, grades = new Map()
  for (const row of rows) grades.set(row.steel_grade, (grades.get(row.steel_grade) || 0) + 1)
  for (const key of ['thickness', 'rough_thickness', 'rolling_thickness', 'exit_temp', 'temp_drop']) {
    const values = rows.map(row => row[key]).filter(present)
    if (values.length) histograms[key] = histogram(values, rows.length - values.length)
    if (values.length && ['exit_temp', 'temp_drop'].includes(key)) scales[key] = {min: Math.min(...values), max: Math.max(...values)}
  }
  const x = request.x_field || 'rough_thickness'
  const scatter = rows.filter(row => present(row[x]) && present(row.temp_drop))
    .map(row => [row[x], row.temp_drop, row.record_id, row.steel_grade])
  const size = request.page_size || 30
  let page = Math.min(request.page || 1, Math.max(1, Math.ceil(rows.length / size)))
  const selectedIndex = rows.findIndex(row => row.record_id === request.selected_id)
  if (request.locate_selected && selectedIndex >= 0) page = Math.floor(selectedIndex / size) + 1
  return {
    dataset_id: quickDataset.id, scope: `${quickDataset.sha256}:${JSON.stringify(filters)}`, filters,
    total: rows.length, source_total: records.length,
    invalid_in_scope: rows.filter(row => row.invalid).length, invalid_in_dataset: quickDataset.quality.invalid_rows,
    grades: [...grades].map(([name, value]) => ({name, value})).sort((a, b) => b.value - a.value || a.name.localeCompare(b.name)),
    histograms, scatter, scatter_valid_n: scatter.length,
    records: rows.slice((page - 1) * size, page * size), page, page_size: size,
    selected: rows[selectedIndex >= 0 ? selectedIndex : 0] || null, color_scales: scales
  }
}

export function quickRecord(id, filters) {
  const row = quickRows(filters).find(row => row.record_id === id)
  if (!row) throw new Error('该记录不在当前筛选范围，请刷新数据')
  return row
}

export function quickCsv(filters) {
  const keys = bundle.columns.filter(key => key !== 'backend_row_index')
  const escaped = value => `"${String(value ?? '').replaceAll('"', '""')}"`
  return '\ufeff' + [keys.join(','), ...quickRows(filters).map(row => keys.map(key => escaped(row[key])).join(','))].join('\r\n') + '\r\n'
}

export function downloadQuickScope(filters) {
  const url = URL.createObjectURL(new Blob([quickCsv(filters)], {type: 'text/csv;charset=utf-8'}))
  const link = document.createElement('a')
  link.href = url; link.download = '快速示例-筛选记录.csv'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
