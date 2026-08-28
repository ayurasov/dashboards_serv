import { api } from './client.js'

export const tpApi = {
  rows:        ()      => api.get('/tp/rows'),
  columns:     ()      => api.get('/tp/columns'),
  summary:     (w=8)   => api.get(`/tp/summary?weeks=${w}`),
  export:      ()      => api.get('/tp/export', { responseType: 'blob' }),
  createRow:   (body)  => api.post('/tp/rows', body),
  updateRow:   (id, b) => api.put(`/tp/rows/${id}`, b),
  deleteRow:   (id)    => api.del(`/tp/rows/${id}`),
  bulkImport:  (rows)  => api.post('/tp/rows/bulk_import', { rows }),
  getSetting:  (key)   => api.get(`/tp/settings/${key}`),
  putSetting:  (key,v) => api.put(`/tp/settings/${key}`, v),
}
