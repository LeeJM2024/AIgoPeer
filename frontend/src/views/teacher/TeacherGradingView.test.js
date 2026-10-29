// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TeacherGradingView from './TeacherGradingView.vue'
import { getGradingWorkspace, getPublicationReadiness, getGradeHistory, correctTeacherGrade, createTeacherGrade, createTeacherFinalReview } from '../../api/teacher'
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
  score_preview:null,score_preview_state:'FINAL_REVIEW_REQUIRED',
}
function workspace(status='TEACHER_GRADING') {
  return {assignment:{title:'微课作业',status,teacher_weight:0.6,designated_review_weight:0.4},submissions:[{...submission}],rubric_items:[{id:1,name:'原理',max_score:100,description:'讲解算法'}]}
}
async function open() {
  wrapper=mount(TeacherGradingView,{attachTo:document.body,global:{stubs:{
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
afterEach(()=>{ wrapper?.unmount(); vi.restoreAllMocks() })

it('材料与评分保持相邻，零分不误判缺失，五人分未齐发布仍禁用',async()=>{
  const view=await open()
  expect(view.findAll('.score-comparison strong').map(item=>item.text())).toEqual(['0','0','—'])
  expect(view.get('.score-preview').text()).toContain('待教师最终复核')
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
  const data=workspace('PUBLISHED_RESULT')
  Object.assign(data.submissions[0],{score_preview:88.5,score_preview_state:'PUBLISHED'})
  getGradingWorkspace.mockResolvedValue(data)
  const view=await open()
  expect(view.get('.score-preview').text()).toContain('最终总分')
  expect(view.get('.score-preview strong').text()).toBe('88.50')
  expect(view.findAll('fieldset')[0].element.disabled).toBe(true)
  expect(view.findAll('button').some(item=>item.text()==='锁定复核最终分')).toBe(false)
})

it('保存更正版本后更新加权总分，并提示最新教师分待锁定',async()=>{
  const data=workspace()
  Object.assign(data.submissions[0],{final_review_status:'NORMAL',teacher_score:90,
    aggregate_score:92.89,score_preview:91.16,score_preview_state:'WEIGHTED'})
  getGradingWorkspace.mockResolvedValue(data)
  const view=await open()
  expect(view.get('.score-preview strong').text()).toBe('91.16')
  await view.findAll('button').find(item=>item.text()==='创建更正版本').trigger('click')
  await view.get('.score-input input').setValue('96.98')
  expect(view.get('.spaced-label input').element.required).toBe(false)
  const corrected=workspace()
  Object.assign(corrected.submissions[0],{final_review_status:'NORMAL',teacher_grade_version:2,
    teacher_score:96.98,aggregate_score:92.89,rubric_scores_json:{1:96.98},locked_at:null,
    score_preview:95.34,score_preview_state:'TEACHER_GRADE_UNLOCKED'})
  getGradingWorkspace.mockResolvedValue(corrected)
  correctTeacherGrade.mockResolvedValue({version:2})
  await view.get('.scoring-column form').trigger('submit')
  await flushPromises()
  expect(correctTeacherGrade).toHaveBeenCalledWith(1,expect.objectContaining({expected_version:1,reason:'',comment:''}))
  expect(view.get('.score-preview strong').text()).toBe('95.34')
  expect(view.get('.score-preview').text()).toContain('教师 60% + 评审 40% · 教师分待锁定')
})

it('正常作业的零分总分保持显示，聚合过期时显示重新聚合提示',async()=>{
  const data=workspace()
  Object.assign(data.submissions[0],{final_review_status:'NORMAL',score_preview:0,score_preview_state:'WEIGHTED'})
  getGradingWorkspace.mockResolvedValue(data)
  const view=await open()
  expect(view.get('.score-preview strong').text()).toBe('0.00')
  view.unmount()
  Object.assign(data.submissions[0],{score_preview:null,score_preview_state:'AGGREGATE_STALE'})
  const stale=await open()
  expect(stale.get('.score-preview strong').text()).toBe('—')
  expect(stale.get('.score-preview').text()).toContain('评审已修改，需重新聚合')
})

it('教师初评可以留空反馈',async()=>{
  const data=workspace()
  Object.assign(data.submissions[0],{teacher_grade_id:null,locked_at:null,final_review_status:'NORMAL'})
  getGradingWorkspace.mockResolvedValue(data)
  const view=await open()
  await view.get('.score-input input').setValue('88')
  expect(view.text()).toContain('教师反馈（选填）')
  await view.get('.scoring-column form').trigger('submit')
  await flushPromises()
  expect(createTeacherGrade).toHaveBeenCalledWith(1,{rubric_scores:[{rubric_item_id:1,score:88}],comment:''})
})

it('高风险复核允许留空理由，零分仍可提交',async()=>{
  vi.spyOn(window,'confirm').mockReturnValue(true)
  const view=await open()
  const form=view.findAll('form').find(item=>item.text().includes('高风险作品复核最终分'))
  expect(form.get('textarea').element.required).toBe(false)
  expect(form.text()).toContain('复核理由（选填）')
  await form.get('input').setValue('0')
  await form.trigger('submit')
  await flushPromises()
  expect(createTeacherFinalReview).toHaveBeenCalledWith(1,{final_score:0,reason:''})
})

it('高风险复核仍要求填写最终分',async()=>{
  const view=await open()
  const form=view.findAll('form').find(item=>item.text().includes('高风险作品复核最终分'))
  await form.trigger('submit')
  await flushPromises()
  expect(createTeacherFinalReview).not.toHaveBeenCalled()
  expect(view.get('[role=alert]').text()).toBe('请填写复核最终分。')
})

it('点击高风险发布阻塞项直接选中对应作品并聚焦复核最终分',async()=>{
  const data=workspace()
  data.submissions.push({...submission,id:2,author_name:'第二位学生',student_no:'D102',anonymous_token:'DEMO-2'})
  getGradingWorkspace.mockResolvedValue(data)
  getPublicationReadiness.mockResolvedValue({ready:false,blockers:[{code:'TEACHER_FINAL_REVIEW_REQUIRED',submission_id:2,author_name:'第二位学生',student_no:'D102'}]})
  const view=await open()
  expect(view.get('#selected-work-heading').text()).toBe('演示学生')
  const action=view.get('.blocker-action')
  expect(action.text()).toContain('第二位学生（D102）')
  const scroll=vi.fn()
  view.get('.final-review-form').element.scrollIntoView=scroll
  await action.trigger('click')
  await flushPromises()
  expect(view.get('#selected-work-heading').text()).toBe('第二位学生')
  expect(getGradeHistory).toHaveBeenLastCalledWith(2)
  expect(scroll).toHaveBeenCalledWith({behavior:'auto',block:'start'})
  expect(document.activeElement).toBe(view.get('.final-review-form input').element)
  expect(createTeacherFinalReview).not.toHaveBeenCalled()
})

it('作品初评阻塞项定位对应作品，通用提示保持文字',async()=>{
  const data=workspace()
  data.submissions.push({...submission,id:2,author_name:'未评分学生',student_no:'D102',teacher_grade_id:null,locked_at:null,final_review_status:'NORMAL'})
  getGradingWorkspace.mockResolvedValue(data)
  getPublicationReadiness.mockResolvedValue({ready:false,blockers:[{code:'TEACHER_GRADE_REQUIRED',submission_id:2,author_name:'未评分学生',student_no:'D102'},{code:'SUBMISSIONS_STILL_OPEN'}]})
  const view=await open()
  expect(view.findAll('.blocker-action')).toHaveLength(1)
  await view.get('.blocker-action').trigger('click')
  await flushPromises()
  expect(view.get('#selected-work-heading').text()).toBe('未评分学生')
  expect(view.find('.final-review-form').exists()).toBe(false)
  expect(document.activeElement).toBe(view.get('.grading-editor').element)
})

it('待处理异常提示链接到当前作业的评审与异常页面',async()=>{
  getPublicationReadiness.mockResolvedValue({ready:false,blockers:[{code:'OPEN_ANOMALIES_REQUIRE_REVIEW',count:5}]})
  const view=await open()
  expect(view.get('.blocker-list a').attributes('href')).toBe('/teacher/assignments/2/reviews')
})
