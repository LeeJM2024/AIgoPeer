import { errorMessages } from './errors'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export async function apiFetch(path, options = {}) {
  // Do not allow an API caller to send a bearer token to an arbitrary URL.
  if (!path.startsWith('/api/') || /[\\\r\n]/.test(path) ||
      /(?:^|\/)\.\.(?:\/|$)/.test(decodeURIComponent(path.split('?')[0])))
    throw new Error('无效的接口地址。')
  const token = localStorage.getItem('algopeer_token')
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData))
    headers.set('Content-Type', 'application/json')
  if (token && !['GET', 'HEAD', 'OPTIONS'].includes((options.method || 'GET').toUpperCase())) {
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    headers.set('X-Request-Nonce', Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join(''))
    headers.set('X-Request-Timestamp', String(Math.floor(Date.now() / 1000)))
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'omit', redirect: 'error' })
  if (response.ok && options.responseType === 'blob') return response.blob()
  const body = await response.json().catch(() => null)
  if (
    response.status === 401 &&
    path !== '/api/auth/login' &&
    token &&
    localStorage.getItem('algopeer_token') === token
  ) {
    localStorage.removeItem('algopeer_token')
    localStorage.removeItem('algopeer_user')
    window.dispatchEvent(new Event('algopeer-session-expired'))
  }
  if (!response.ok) {
    const detail = body?.message ?? body?.detail
    const code =
      body?.code ?? (typeof detail === 'string' ? detail : detail?.code)
    const message =
      errorMessages[code] ??
      (response.status === 422
        ? '输入内容不符合要求，请检查必填项、时间和分值精度。'
        : typeof detail === 'string'
          ? detail
          : `请求失败：${response.status}`)
    const error = new Error(message)
    error.status = response.status
    error.details = body?.details ?? detail
    error.code = code
    throw error
  }
  return body.data ?? body
}
