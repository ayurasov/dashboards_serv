/**
 * API client for the Technical Support dashboard (/api/tp/*).
 * Mirrors the endpoint structure of tp-report but calls the unified FastAPI backend.
 */
import { useAuthStore } from '../stores/auth.js'

const BASE = '/api/tp'

function headers() {
  const auth = useAuthStore()
  return {
    'Content-Type': 'application/json',
    ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
  }
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail || res.statusText)
  }
  return res.json()
}

// ── Rows ──────────────────────────────────────────────────────────────────────
export const tpApi = {
  /** Fetch all weekly rows, optionally filtered by year */
  getRows(year) {
    const q = year !== undefined ? `?year=${year}` : ''
    return request('GET', `/rows${q}`)
  },

  createRow(data)   { return request('POST',   '/rows', data) },
  updateRow(id, data) { return request('PUT',  `/rows/${id}`, data) },
  deleteRow(id)     { return request('DELETE', `/rows/${id}`) },

  /** Replace all rows with supplied list. Admin-only. */
  bulkImport(rows)  { return request('POST', '/rows/bulk_import', { rows }) },

  // ── Settings ───────────────────────────────────────────────────────────────
  getTrafficRules()        { return request('GET',  '/settings/traffic_rules') },
  putTrafficRules(body)    { return request('PUT',  '/settings/traffic_rules', body) },

  getBlockSettings()       { return request('GET',  '/settings/block_settings') },
  putBlockSettings(body)   { return request('PUT',  '/settings/block_settings', body) },

  getColorPalette()        { return request('GET',  '/settings/color_palette') },
  putColorPalette(body)    { return request('PUT',  '/settings/color_palette', body) },
  resetColorPalette()      { return request('DELETE', '/settings/color_palette') },
}
