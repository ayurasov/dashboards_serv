import { useAuthStore } from '../stores/auth.js'

const BASE = '/api/tp'

function headers() {
  const auth = useAuthStore()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${auth.token}`,
  }
}

export const tpApi = {
  // ---- rows ----
  async getRows() {
    const r = await fetch(`${BASE}/rows`, { headers: headers() })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async createRow(body) {
    const r = await fetch(`${BASE}/rows`, { method: 'POST', headers: headers(), body: JSON.stringify(body) })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async updateRow(id, body) {
    const r = await fetch(`${BASE}/rows/${id}`, { method: 'PUT', headers: headers(), body: JSON.stringify(body) })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async deleteRow(id) {
    const r = await fetch(`${BASE}/rows/${id}`, { method: 'DELETE', headers: headers() })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async bulkImport(rows) {
    const r = await fetch(`${BASE}/rows/bulk_import`, { method: 'POST', headers: headers(), body: JSON.stringify({ rows }) })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },

  // ---- settings ----
  async getSetting(key) {
    const r = await fetch(`${BASE}/settings/${key}`, { headers: headers() })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async putSetting(key, body) {
    const r = await fetch(`${BASE}/settings/${key}`, { method: 'PUT', headers: headers(), body: JSON.stringify(body) })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
  async resetPalette() {
    const r = await fetch(`${BASE}/settings/color_palette`, { method: 'DELETE', headers: headers() })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },
}
