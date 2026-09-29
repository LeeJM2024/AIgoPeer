const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('algopeer_token')
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const body = await response.json().catch(() => null)
  if (response.status === 401 && path !== '/api/auth/login') {
    localStorage.removeItem('algopeer_token')
    localStorage.removeItem('algopeer_user')
  }
  if (!response.ok) {
    const detail = body?.message ?? body?.detail
    const message = typeof detail === 'string' ? detail : detail?.code ?? `请求失败：${response.status}`
    const error = new Error(message)
    error.status = response.status
    error.details = detail
    throw error
  }
  return body.data ?? body
}
