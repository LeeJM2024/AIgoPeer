const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('algopeer_token')
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.message ?? body?.detail ?? `请求失败：${response.status}`)
  return body.data ?? body
}
