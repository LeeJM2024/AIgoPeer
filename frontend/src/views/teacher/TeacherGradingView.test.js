// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TeacherGradingView from './TeacherGradingView.vue'
import { getGradingWorkspace, getPublicationReadiness, getGradeHistory } from '../../api/teacher'
import { currentUser } from '../../api/auth'

vi.mock('vue-router',async importOriginal=>({...(await importOriginal()),useRoute:()=>({params:{id:'2'}})}))
vi.mock('../../api/auth',()=>({currentUser:vi.fn()}))
vi.mock('../../api/teacher',()=>({
  getGradingWorkspace:vi.fn(),getPublicationReadiness:vi.fn(),getGradeHistory:vi.fn(),
  createTeacherGrade:vi.fn(),correctTeacherGrade:vi.fn(),lockTeacherGrade:vi.fn(),
  publishResults:vi.fn(),createTeacherFinalReview:vi.fn(),
}))
let wrapper
const submission = {
  id:1,author_name:'演示学生',student_no:'D101',class_name:'1班',anonymous_token:'DEMO-1',
  status:'VALID',material_status:'VALID',aggregate_score:0,teacher_score:0,
  teacher_grade_id:1,teacher_grade_version:1,locked_at:'2026-10-16T00:00:00Z',
  final_review_status:'ESCALATED_FOR_TEACHER_FINAL_REVIEW',rubric_scores_json:{1:0},
}
function workspace(status='TEACHER_GRADING') {
  return {assignment:{title:'微课作业',status},submissions:[{...submission}],rubric_items:[{id:1,name:'原理',max_score:100,description:'讲解算法'}]}
}
async function open() {
  wrapper=mount(TeacherGradingView,{global:{stubs:{
    SubmissionEvidence:{props:['submissionId'],template:'<section class="evidence-stub">真实材料入口 {{submissionId}}</section>'},
    RouterLink:{props:['to'],template:'<a :href="to"><slot /></a>'},
  }}})
  await flushPromises()
  return wrapper
}
beforeEach(()=>{
  vi.resetAllMocks()
  currentUser.mockReturnValue({id:10,role:'TEACHER'})
  getGradingWorkspace.mockResolvedValue(workspace())
  getPublicationReadiness.mockResolvedValue({ready:false,blockers:[{code:'REVIEW_COUNT_INCOMPLETE'}],submission_count:1})
  getGradeHistory.mockResolvedValue([{id:1,version:1,entered_by:10,total_score:0,rubric_scores_json:{1:0},locked_at:submission.locked_at}])
})
afterEach(()=>wrapper?.unmount())

it('材料与评分保持相邻，零分不误判缺失，五人分未齐发布仍禁用',async()=>{
  const view=await open()
  expect(view.findAll('.score-comparison strong').map(item=>item.text())).toEqual(['0','0'])
  expect(view.get('.grading-content .evidence-stub').text()).toContain('真实材料入口 1')
  expect(view.get('.grading-content .scoring-column').exists()).toBe(true)
  const publish=view.findAll('button').find(item=>item.text()==='发布全部成绩')
  expect(publish.element.disabled).toBe(true)
  expect(view.text()).toContain('高风险作品复核最终分')
  expect(view.findAll('button').find(item=>item.text()==='锁定复核最终分').element.disabled).toBe(false)
})

it('不是初评教师时仍不可锁定复核最终分',async()=>{
  currentUser.mockReturnValue({id:20,role:'TEACHER'})
  const view=await open()
  expect(view.findAll('button').find(item=>item.text()==='锁定复核最终分').element.disabled).toBe(true)
})

it('已发布结果保持只读，不出现复核最终分提交表单',async()=>{
  getGradingWorkspace.mockResolvedValue(workspace('PUBLISHED_RESULT'))
  const view=await open()
  expect(view.findAll('fieldset')[0].element.disabled).toBe(true)
  expect(view.findAll('button').some(item=>item.text()==='锁定复核最终分')).toBe(false)
})
