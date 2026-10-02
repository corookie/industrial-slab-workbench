const configuredApiBase = String(import.meta.env.VITE_API_BASE || '').trim().replace(/\/+$/, '')
// VITE_API_BASE may be either the service origin (recommended) or an origin
// ending in /api.  Keeping /api here lets the local Vite proxy keep working.
const apiRoot = configuredApiBase
  ? (configuredApiBase.endsWith('/api') ? configuredApiBase : `${configuredApiBase}/api`)
  : '/api'

export function apiUrl(path = '') {
  const value = String(path || '')
  if (/^https?:\/\//i.test(value)) return value

  const normalized = value.startsWith('/') ? value : `/${value}`
  const suffix = normalized === '/api'
    ? ''
    : (normalized.startsWith('/api/') ? normalized.slice(4) : normalized)
  return `${apiRoot}${suffix}`
}

export async function api(path, body, method = 'POST') {
  const isForm = body instanceof FormData
  const res = await fetch(apiUrl(path), {
    method, headers: body && !isForm ? { 'Content-Type': 'application/json' } : {},
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined
  })
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const data = await res.json()
      msg = Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('；') : data.detail || msg
    } catch { /* server may return plain text */ }
    throw new Error(msg)
  }
  return res.json()
}
export const get = path => api(path, null, 'GET')
export const fmt = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
export const htmlEscape = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
export async function downloadScope(dataset, filters) {
  const r = await fetch(apiUrl(`/datasets/${dataset}/export`), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(filters)})
  if(!r.ok) throw new Error('当前范围导出失败')
  const url=URL.createObjectURL(await r.blob()), a=document.createElement('a')
  a.href=url; a.download='筛选记录.csv'; a.click()
  setTimeout(()=>URL.revokeObjectURL(url),1000)
}
