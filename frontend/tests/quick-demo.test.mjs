import test from 'node:test'
import assert from 'node:assert/strict'
import {quickDataset, quickQuery, quickRows, quickRecord, quickCsv} from '../src/quick-demo.js'

test('bundled simulation has 1,000 unique records and exactly five grades', () => {
  const q = quickQuery()
  assert.equal(q.total, 1000)
  assert.equal(new Set(quickRows().map(row => row.record_id)).size, 1000)
  assert.equal(quickDataset.release.data_origin, 'independent_simulation')
  assert.deepEqual(q.grades, ['G01','G02','G03','G04','G05'].map(name => ({name, value:200})))
  assert.equal(q.selected.slab_id, 'SIM-008318')
  for (const hist of Object.values(q.histograms)) assert.equal(hist.counts.reduce((a,b) => a+b, 0), q.total)
  assert.equal(q.scatter.length, q.total)
  assert.equal(q.records.length, 30)
})

test('combined filters match an independently checked reference count', () => {
  const filters = {grades:['G03'],ranges:{exit_temp:[1180,1210],rough_thickness:[34,42],process_time:[150,210]}}
  const q = quickQuery({filters})
  assert.equal(q.total, 81)
  assert.deepEqual(q.records.slice(0,3).map(row => row.slab_id), ['SIM-005223','SIM-004952','SIM-004154'])
  assert.deepEqual(q.grades, [{name:'G03',value:81}])
  assert.equal(q.histograms.temp_drop.valid_n, 81)
  assert.equal(q.histograms.temp_drop.counts.reduce((a,b) => a+b,0), 81)
  assert.equal(q.scatter.length, 81)
  const scopeIds = new Set(quickRows(filters).map(row => row.record_id))
  assert.ok(q.records.every(row => scopeIds.has(row.record_id)))
  assert.ok(q.scatter.every(point => scopeIds.has(point[2])))
  assert.equal(quickCsv(filters).split('\r\n').length - 2, 81)
})

test('pagination, point selection and three-dimensional record use the same scope', () => {
  const end = quickQuery({page:999})
  assert.equal(end.page, 34)
  assert.equal(end.records.length, 10)
  const target = end.records.at(-1)
  const located = quickQuery({selected_id:target.record_id,locate_selected:true})
  assert.equal(located.page, 34)
  assert.equal(located.selected.record_id, target.record_id)
  assert.deepEqual(quickRecord(target.record_id, located.filters), located.selected)
  assert.ok(located.records.some(row => row.record_id === target.record_id))
  assert.throws(() => quickRecord(target.record_id,{grades:['G01']}), /不在当前筛选范围/)
})

test('date endpoints include the full day; empty and constant ranges are supported', () => {
  const day = quickQuery({filters:{date_start:'2024-07-10',date_end:'2024-07-10'}})
  assert.equal(day.total, 29)
  assert.equal(day.records[0].slab_id, 'SIM-003228')
  assert.ok(day.records.every(row => row.produced_at.startsWith('2024-07-10')))
  const empty = quickQuery({filters:{ranges:{rough_thickness:[999,1000]}}})
  assert.equal(empty.total, 0)
  assert.equal(empty.selected, null)
  assert.equal(empty.page, 1)
  assert.equal(empty.scatter.length, 0)
  const constant = quickQuery({filters:{ranges:{thickness:[230,230]}}})
  assert.equal(constant.histograms.thickness.counts.length, 1)
  assert.equal(constant.histograms.thickness.counts[0], constant.total)
})

test('invalid boundaries are rejected and export preserves simulation labels', () => {
  assert.throws(() => quickRows({ranges:{exit_temp:[1300,1100]}}), /下限不能大于上限/)
  assert.throws(() => quickRows({ranges:{bad_field:[0,1]}}), /支持的数值字段/)
  assert.throws(() => quickRows({ranges:{temp_drop:[NaN,null]}}), /有限边界/)
  assert.throws(() => quickRows({date_start:'2024-07-20',date_end:'2024-07-01'}), /起始日期/)
  const csv = quickCsv({grades:['G01']})
  assert.equal(csv.split('\r\n').length - 2, 200)
  assert.ok(csv.includes('完全独立模拟示例；非真实生产记录'))
  assert.ok(!csv.includes('backend_row_index'))
})
