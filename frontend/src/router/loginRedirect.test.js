import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it } from 'vitest'
import { loginRedirect } from './loginRedirect'

const router = createRouter({ history: createMemoryHistory(), routes: [
  { path: '/', redirect: '/login' },
  { path: '/login', component: {}, meta: { public: true } },
  { path: '/register', component: {}, meta: { public: true } },
  { path: '/teacher', component: {}, meta: { teacher: true } },
  { path: '/student', component: {}, meta: { student: true } },
  { path: '/student/assignments/:id/grade', component: {}, meta: { student: true } },
  { path: '/reviewer/tasks', component: {}, meta: { student: true } },
] })

it.each([undefined, ['/student'], 'https://example.invalid', '//example.invalid',
  '/\\example.invalid', '/missing', '/login?redirect=/teacher', '/register', '/', '/teacher', '/student\n']) (
  '学生登录拒绝不可用返回地址 %s', target => {
    expect(loginRedirect(router, target, 'STUDENT')).toBe('/student')
  },
)
it.each(['/student/assignments/12/grade?tab=current#score', '/reviewer/tasks?page=2']) (
  '保留学生可用页面及查询参数 %s', target => {
    expect(loginRedirect(router, target, 'STUDENT')).toBe(target)
  },
)
it('教师可返回教师页面，无效地址回到教师工作台', () => {
  expect(loginRedirect(router, '/teacher?tab=all', 'TEACHER')).toBe('/teacher?tab=all')
  expect(loginRedirect(router, '/unknown', 'TEACHER')).toBe('/teacher')
})

it.each(['/student', '/student/assignments/12/grade', '/reviewer/tasks']) (
  '教师登录拒绝学生专用返回地址 %s', target => {
    expect(loginRedirect(router, target, 'TEACHER')).toBe('/teacher')
  },
)
