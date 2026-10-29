// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import TeacherClassesView from './TeacherClassesView.vue'
import { getClasses, getClassStudents, importStudents } from '../../api/teacher'

vi.mock('../../api/teacher', () => ({
  getClasses: vi.fn(), getClassStudents: vi.fn(), importStudents: vi.fn(),
  createClass: vi.fn(), editClass: vi.fn(), removeEnrollment: vi.fn(),
}))
let wrapper
afterEach(() => { wrapper?.unmount(); vi.resetAllMocks() })

it('教师分别填写学号、姓名、初始密码，姓名随账号提交并显示在名册', async () => {
  getClasses.mockResolvedValue([{ id: 3, name: '演示班', course_term: '2026', student_count: 0 }])
  getClassStudents.mockResolvedValueOnce([]).mockResolvedValueOnce([{ id: 7, student_no: 'S001', name: '王小明' }])
  importStudents.mockResolvedValue({ created_accounts: 1, new_enrollments: 1, unchanged: 0 })
  wrapper = mount(TeacherClassesView)
  await flushPromises()
  await wrapper.get('#student-account').setValue(' S001 ')
  await wrapper.get('#student-display-name').setValue(' 王小明 ')
  await wrapper.get('#student-initial-password').setValue('InitialPassword!')
  await wrapper.get('form[aria-label="添加学生"]').trigger('submit')
  await flushPromises()
  expect(importStudents).toHaveBeenCalledExactlyOnceWith(3, [{ student_no: 'S001', name: '王小明', password: 'InitialPassword!' }])
  expect(wrapper.get('tbody').text()).toContain('王小明')
  expect(wrapper.get('#student-initial-password').element.value).toBe('')
})

async function openBatchImport() {
  getClasses.mockResolvedValue([{ id: 3, name: '演示班', course_term: '2026', student_count: 0 }])
  getClassStudents.mockResolvedValue([])
  importStudents.mockResolvedValue({ created_accounts: 1, new_enrollments: 1, unchanged: 0 })
  wrapper = mount(TeacherClassesView)
  await flushPromises()
  return wrapper.get('form[aria-label="批量添加学生"]')
}

it.each([' ', '   ', '\u3000', '\t'])('批量导入支持分隔符 %j', async (separator) => {
  const form = await openBatchImport()
  await form.get('textarea').setValue(['S001', '王小明', 'InitialPassword!'].join(separator))
  await form.trigger('submit')
  await flushPromises()
  expect(importStudents).toHaveBeenCalledExactlyOnceWith(3, [
    { student_no: 'S001', name: '王小明', password: 'InitialPassword!' },
  ])
  expect(form.get('textarea').element.value).toBe('')
})

it('表格导入保留姓名及密码里的空格，并支持已有账号不填密码', async () => {
  const form = await openBatchImport()
  await form.get('textarea').setValue('S001\t王 小明\t Initial Password! \r\n\r\nS002 张小红\nS003\t李小白\t')
  await form.trigger('submit')
  await flushPromises()
  expect(importStudents).toHaveBeenCalledExactlyOnceWith(3, [
    { student_no: 'S001', name: '王 小明', password: ' Initial Password! ' },
    { student_no: 'S002', name: '张小红', password: undefined },
    { student_no: 'S003', name: '李小白', password: undefined },
  ])
})

it('格式错误显示在名单旁并保留输入，任何一行错误都不发送导入请求', async () => {
  const form = await openBatchImport()
  const input = 'S001 王小明 InitialPassword!\n\nS002\t\tInitialPassword!'
  await form.get('textarea').setValue(input)
  await form.trigger('submit')
  await flushPromises()
  expect(importStudents).not.toHaveBeenCalled()
  expect(form.get('[role="alert"]').text()).toContain('第 3 行格式不正确')
  expect(form.get('textarea').attributes('aria-invalid')).toBe('true')
  expect(form.get('textarea').element.value).toBe(input)
})

it('接口返回的导入错误也在输入框旁显示', async () => {
  const form = await openBatchImport()
  importStudents.mockRejectedValue(new Error('学号已存在，姓名与原账号不一致。'))
  await form.get('textarea').setValue('S001 王小明 InitialPassword!')
  await form.trigger('submit')
  await flushPromises()
  expect(form.get('[role="alert"]').text()).toContain('姓名与原账号不一致')
})
