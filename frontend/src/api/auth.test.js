// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'
import { apiFetch } from './client'
import { changePassword, logout } from './auth'

vi.mock('./client', () => ({ apiFetch: vi.fn() }))
beforeEach(() => { localStorage.clear(); vi.resetAllMocks() })

it('改密后保存换发的会话令牌', async () => {
  localStorage.setItem('algopeer_token', 'previous')
  apiFetch.mockResolvedValue({ changed: true, access_token: 'rotated' })
  await changePassword('old', 'new', 'new')
  expect(localStorage.getItem('algopeer_token')).toBe('rotated')
})

it('改密旧请求返回时不覆盖其他标签页的新登录', async () => {
  localStorage.setItem('algopeer_token', 'previous')
  let finish
  apiFetch.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const pending = changePassword('old', 'new', 'new')
  localStorage.setItem('algopeer_token', 'another-login')
  finish({ changed: true, access_token: 'rotated' })
  await pending
  expect(localStorage.getItem('algopeer_token')).toBe('another-login')
})

it('退出在服务端撤销成功后清除本地身份', async () => {
  localStorage.setItem('algopeer_token', 'previous')
  localStorage.setItem('algopeer_user', '{"role":"STUDENT"}')
  let finish
  apiFetch.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const pending = logout()
  expect(apiFetch).toHaveBeenCalledWith('/api/auth/logout', { method: 'POST' })
  expect(localStorage.getItem('algopeer_token')).toBe('previous')
  finish({ logged_out: true })
  await pending
  expect(localStorage.getItem('algopeer_token')).toBeNull()
  expect(localStorage.getItem('algopeer_user')).toBeNull()
})

it('服务端撤销失败时保留会话供重试', async () => {
  localStorage.setItem('algopeer_token', 'previous')
  apiFetch.mockRejectedValue(new Error('network failure'))
  await expect(logout()).rejects.toThrow('network failure')
  expect(localStorage.getItem('algopeer_token')).toBe('previous')
})
