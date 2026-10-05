import bundle from './data/quick-analysis.json' with { type: 'json' }
import { quickDataset } from './quick-demo.js'

const canonical = value => Array.isArray(value) ? value.map(canonical)
  : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value
const stable = value => JSON.stringify(canonical(value))

// No network call and no invented calculation. The JSON is an actual Python
// analysis of the same immutable rows used by quickQuery.
export function savedQuickAnalysis() {
  if (bundle.result.quick_dataset_sha256 !== quickDataset.sha256)
    throw new Error('内置分析与数据版本不一致，请刷新网页')
  return structuredClone(bundle)
}

export function quickAnalysisMatchesScope(result, filters) {
  const normalized = {grades: [], ranges: {}, date_start: null, date_end: null, exclude_invalid: true, ...filters}
  return result?.quick_dataset_sha256 === quickDataset.sha256 && stable(result.parameters.filters) === stable(normalized)
}

export function quickArtifactUrl(result, name, base = import.meta.env?.BASE_URL || '/') {
  const path = result.artifacts[name]
  if (!path?.startsWith('quick-analysis/') || path.includes('..'))
    throw new Error('内置分析文件路径无效')
  return `${base ?? '/'}${path}`
}
