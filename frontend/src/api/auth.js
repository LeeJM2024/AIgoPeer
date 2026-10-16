import { apiFetch } from './client'

export function register(studentNo, name, password) {
  return apiFetch('/api/auth/register', {
    method: 'POST', body: JSON.stringify({ student_no: studentNo, name, password }),
  })
}

export async function login(account, password) {
  const result = await apiFetch('/api/auth/login', {
    method: 'POST', body: JSON.stringify({ account, password })
  })
  localStorage.setItem('algopeer_token', result.access_token)
  localStorage.setItem('algopeer_user', JSON.stringify(result.user))
  return result.user
}

export function currentUser() {
  try { return JSON.parse(localStorage.getItem('algopeer_user')) }
  catch { return null }
}

export function logout() {
  localStorage.removeItem('algopeer_token')
  localStorage.removeItem('algopeer_user')
}
