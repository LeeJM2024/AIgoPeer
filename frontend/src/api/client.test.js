// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiFetch } from './client'

const unauthorized = () => new Response(JSON.stringify({ code: 'UNAUTHORIZED' }), { status: 401 })
beforeEach(() => localStorage.clear())
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('写请求生成不同的安全随机编号与时间戳，不跟随重定向', async () => {
  localStorage.setItem('algopeer_token', 'token')
  const send = vi.fn(async () => new Response('{"data":{}}'))
  vi.stubGlobal('fetch', send)
  await apiFetch('/api/teacher/classes', { method: 'POST', body: '{}' })
  await apiFetch('/api/teacher/classes', { method: 'POST', body: '{}' })
  const first = send.mock.calls[0][1]
  const second = send.mock.calls[1][1]
  expect(first.headers.get('X-Request-Nonce')).toMatch(/^[a-f0-9]{32}$/)
  expect(first.headers.get('X-Request-Nonce')).not.toBe(second.headers.get('X-Request-Nonce'))
  expect(Number(first.headers.get('X-Request-Timestamp'))).toBeGreaterThan(Date.now() / 1000 - 5)
  expect(first.redirect).toBe('error')
  expect(first.credentials).toBe('omit')
})

it('拒绝向外站或有路径穿越的地址发送令牌', async () => {
  const send = vi.fn()
  vi.stubGlobal('fetch', send)
  for (const path of ['https://evil.invalid/api', '//evil.invalid/api', '/api/../secret', '/api/\\evil'])
    await expect(apiFetch(path)).rejects.toThrow('无效的接口地址')
  expect(send).not.toHaveBeenCalled()
})

it('旧请求的 401 不清除新登录的会话', async () => {
  localStorage.setItem('algopeer_token', 'old-token')
  let finish
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve })))
  const expired = vi.spyOn(window, 'dispatchEvent')
  const pending = apiFetch('/api/reviewer/eligibility').catch(error => error)
  localStorage.setItem('algopeer_token', 'new-token')
  localStorage.setItem('algopeer_user', '{"role":"STUDENT"}')
  finish(unauthorized())
  expect((await pending).status).toBe(401)
  expect(localStorage.getItem('algopeer_token')).toBe('new-token')
  expect(localStorage.getItem('algopeer_user')).toContain('STUDENT')
  expect(expired).not.toHaveBeenCalled()
})

it('当前会话失效清除身份并仅通知一次', async () => {
  localStorage.setItem('algopeer_token', 'current-token')
  localStorage.setItem('algopeer_user', '{}')
  vi.stubGlobal('fetch', vi.fn(async () => unauthorized()))
  const expired = vi.spyOn(window, 'dispatchEvent')
  await Promise.all([apiFetch('/api/a').catch(() => {}), apiFetch('/api/b').catch(() => {})])
  expect(localStorage.getItem('algopeer_token')).toBeNull()
  expect(localStorage.getItem('algopeer_user')).toBeNull()
  expect(expired).toHaveBeenCalledTimes(1)
  expect(expired.mock.calls[0][0].type).toBe('algopeer-session-expired')
})

it('未携带身份的旧请求不清除后来登录的会话', async () => {
  let finish
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve })))
  const pending = apiFetch('/api/a').catch(() => {})
  localStorage.setItem('algopeer_token', 'new-token')
  finish(unauthorized())
  await pending
  expect(localStorage.getItem('algopeer_token')).toBe('new-token')
})

it('登录失败不触发当前会话过期', async () => {
  localStorage.setItem('algopeer_token', 'current-token')
  vi.stubGlobal('fetch', vi.fn(async () => unauthorized()))
  await expect(apiFetch('/api/auth/login')).rejects.toMatchObject({ status: 401 })
  expect(localStorage.getItem('algopeer_token')).toBe('current-token')
})

it('退出后到达的旧 401 不重复触发过期导航', async () => {
  localStorage.setItem('algopeer_token', 'old-token')
  let finish
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve })))
  const expired = vi.spyOn(window, 'dispatchEvent')
  const pending = apiFetch('/api/a').catch(() => {})
  localStorage.removeItem('algopeer_token')
  localStorage.removeItem('algopeer_user')
  finish(unauthorized())
  await pending
  expect(expired).not.toHaveBeenCalled()
  expect(localStorage.getItem('algopeer_token')).toBeNull()
})
