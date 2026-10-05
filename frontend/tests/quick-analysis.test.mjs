import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { quickDataset, quickRows, quickQuery } from '../src/quick-demo.js'
import { savedQuickAnalysis, quickAnalysisMatchesScope, quickArtifactUrl } from '../src/quick-analysis.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../public/quick-analysis')
const mean = values => values.reduce((sum, value) => sum + value, 0) / values.length
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`)

test('saved experiment applies the exact embedded 1,000-row dataset', () => {
  const {result} = savedQuickAnalysis()
  assert.equal(result.precomputed, true)
  assert.equal(result.quick_dataset_sha256, quickDataset.sha256)
  assert.equal(result.release.data_origin, 'independent_simulation')
  assert.equal(result.dataset_id, quickDataset.id)
  assert.equal(result.counts.source, 1000)
  assert.equal(result.counts.current_scope, quickQuery({filters: result.parameters.filters}).total)
  assert.equal(result.parameters.steel_grade, 'G01')
  assert.deepEqual(result.parameters.controls, {exit_temp: [1170, 1230], process_time: [140, 220]})
  assert.deepEqual(result.parameters.bins, [24, 32, 36, 44])
})

test('group counts, means and sample standard deviations match frontend rows', () => {
  const {result} = savedQuickAnalysis(), p = result.parameters
  const rows = quickRows(p.filters).filter(row => row.steel_grade === p.steel_grade
    && Object.entries(p.controls).every(([key, [lo, hi]]) => row[key] >= lo && row[key] <= hi))
  assert.equal(rows.length, 182)
  assert.deepEqual(result.groups.map(group => group.n), [49, 87, 46])
  let count = 0
  result.groups.forEach((group, index) => {
    const values = rows.filter(row => row[p.variable] >= p.bins[index]
      && (index === result.groups.length - 1 ? row[p.variable] <= p.bins[index + 1] : row[p.variable] < p.bins[index + 1]))
      .map(row => row.temp_drop)
    assert.equal(group.n, values.length)
    close(group.mean, mean(values))
    close(group.sd, Math.sqrt(values.reduce((sum, value) => sum + (value - mean(values)) ** 2, 0) / (values.length - 1)))
    count += values.length
  })
  assert.equal(count, result.counts.analyzed)
  assert.equal(result.relationships.n, count)
})

test('saved three-dimensional samples locate the same embedded records', () => {
  const {result, conditions} = savedQuickAnalysis(), p = result.parameters
  assert.equal(conditions.analysis_id, result.id)
  assert.equal(conditions.samples_sha256, result.samples_sha256)
  assert.equal(conditions.counts.rendered, result.counts.analyzed)
  const expected = quickRows(p.filters).filter(row => row.steel_grade === p.steel_grade
    && Object.entries(p.controls).every(([key, [lo, hi]]) => row[key] >= lo && row[key] <= hi)
    && row[p.variable] >= p.bins[0] && row[p.variable] <= p.bins.at(-1))
  assert.deepEqual(new Set(conditions.points.map(row => row.record_id)), new Set(expected.map(row => row.record_id)))
  const byId = new Map(expected.map(row => [row.record_id, row]))
  for (const point of conditions.points) {
    const row = byId.get(point.record_id)
    for (const key of ['slab_id', 'steel_grade', 'exit_temp', 'process_time', 'rough_thickness', 'temp_drop']) assert.equal(point[key], row[key])
  }
})

test('filter changes cannot relabel a precomputed result as a new computation', () => {
  const {result} = savedQuickAnalysis()
  assert.equal(quickAnalysisMatchesScope(result, result.parameters.filters), true)
  assert.equal(quickAnalysisMatchesScope(result, {exclude_invalid: true, date_end: null, date_start: null, ranges: {}, grades: []}), true)
  assert.equal(quickAnalysisMatchesScope(result, {...result.parameters.filters, grades: ['G01']}), false)
  assert.equal(quickAnalysisMatchesScope(result, {...result.parameters.filters, ranges: {exit_temp: [1180, 1210]}}), false)
  result.parameters.controls.exit_temp[0] = 0
  assert.equal(savedQuickAnalysis().result.parameters.controls.exit_temp[0], 1170)
})

test('all plots and downloads are local checked-in artifacts, including Pages base', () => {
  const {result, files_sha256} = savedQuickAnalysis()
  for (const [name, sha] of Object.entries(files_sha256)) {
    assert.equal(createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex'), sha)
  }
  for (const name of Object.keys(result.artifacts)) {
    assert.equal(quickArtifactUrl(result, name, '/industrial-slab-workbench/'), `/industrial-slab-workbench/quick-analysis/${name}`)
    assert.equal(quickArtifactUrl(result, name), `/quick-analysis/${name}`)
  }
  assert.ok(fs.readFileSync(path.join(root, 'figure.png')).subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])))
  assert.ok(fs.readFileSync(path.join(root, 'figure.pdf'), 'utf8').startsWith('%PDF-'))
  assert.ok(fs.readFileSync(path.join(root, 'report.html'), 'utf8').includes('完全独立模拟示例'))
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(root, 'result.json'), 'utf8')), result)
})
