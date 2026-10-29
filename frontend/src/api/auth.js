import { apiFetch } from './client'

export async function changePassword(currentPassword, newPassword, confirmPassword) {
  const previous = localStorage.getItem('algopeer_token')
  const result = await apiFetch('/api/auth/change-password', {
    method: 'POST', body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  })
  if (previous && localStorage.getItem('algopeer_token') === previous)
    localStorage.setItem('algopeer_token', result.access_token)
  return result
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

export async function logout() {
  // Start the revocation request while the current token is still available.
  const previous = localStorage.getItem('algopeer_token')
  const pending = previous
    ? apiFetch('/api/auth/logout', { method: 'POST' })
    : Promise.resolve()
  await pending
  if (localStorage.getItem('algopeer_token') === previous) {
    localStorage.removeItem('algopeer_token')
    localStorage.removeItem('algopeer_user')
  }
}
