<script setup>
defineProps({
  assignments: {
    type: Array,
    required: true
  }
})

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short'
})

const stateLabel = (status) => ({ PUBLISHED: '进行中', SUBMITTING: '提交中', REVIEWER_INITIALIZING: '分配评审中', REVIEWER_GRADING: '跨班评审中', AGGREGATING: '汇总评审中', TEACHER_GRADING: '教师评分中' }[status] || '状态待更新')

const formatDeadline = (value) => value ? dateFormatter.format(new Date(value)) : '未设置'

const submissionClosed = (assignment) =>
  assignment.submit_deadline && new Date(assignment.submit_deadline).getTime() <= Date.now()

const submissionLabel = (assignment) => {
  if (assignment.type === 'PROGRAMMING') {
    if (!assignment.submission) return '未提交'
    return `最近一次：${codeStatusLabel(assignment.submission.status)}`
  }
  if (!assignment.submission) return '未提交'
  if (!assignment.submission.material_check_status) return `已提交（${materialStatusLabel(assignment.submission.status)}）`
  return `已提交（材料检查：${materialStatusLabel(assignment.submission.material_check_status)}）`
}
const materialStatusLabel = (status) => ({ VALID: '通过', INVALID: '未通过', PENDING: '检查中', SUPERSEDED: '历史版本', SUBMITTED: '已提交' }[status] || status)

const codeStatusLabel = (status) => ({
  QUEUED: '排队中', RUNNING: '判题中', AC: '通过', WA: '答案错误',
  TLE: '超出时间限制', RE: '运行错误', CE: '编译错误', SYSTEM_ERROR: '判题异常'
}[status] ?? status)

const actionLabel = (assignment) => {
  if (assignment.type === 'FINAL_PROJECT') return submissionClosed(assignment) || !['PUBLISHED', 'SUBMITTING'].includes(assignment.status)
    ? '查看提交与材料检查' : assignment.submission ? '查看并重新上传' : '认领并上传'
  if (submissionClosed(assignment)) return '查看题目与结果'
  if (!assignment.submission) return '查看题目并提交'
  return ['QUEUED', 'RUNNING'].includes(assignment.submission.status) ? '查看判题进度' : '继续编写'
}
</script>

<template>
  <ul class="assignment-list" aria-label="我的作业列表">
    <li v-for="assignment in assignments" :key="assignment.id" class="assignment-card" :data-kind="assignment.type">
      <div class="assignment-card__cover" aria-hidden="true">
        <span>{{ assignment.type === 'PROGRAMMING' ? '编程练习' : '课程项目' }}</span>
        <svg v-if="assignment.type === 'PROGRAMMING'" viewBox="0 0 210 100" fill="none"><path d="m65 24-30 26 30 26M145 24l30 26-30 26M117 15 94 85" stroke="currentColor" stroke-width="8" stroke-linecap="square" /></svg>
        <svg v-else viewBox="0 0 210 100" fill="none"><path d="M105 22 57 53 30 82M57 53l25 29M105 22l48 31-25 29M153 53l27 29" stroke="currentColor" stroke-width="3" /><g fill="currentColor"><rect x="96" y="13" width="18" height="18" rx="3" /><rect x="49" y="45" width="16" height="16" rx="3" /><rect x="145" y="45" width="16" height="16" rx="3" /><circle cx="30" cy="82" r="7" /><circle cx="82" cy="82" r="7" /><circle cx="128" cy="82" r="7" /><circle cx="180" cy="82" r="7" /></g></svg>
      </div>
      <div class="assignment-card__body">
      <div class="assignment-card__heading">
        <div class="assignment-card__title">
          <h2>{{ assignment.title }}</h2>
        </div>
        <span class="status-badge" :data-state="assignment.status">{{ assignment.status === 'PUBLISHED_RESULT' ? '成绩已发布' : submissionClosed(assignment) ? '已截止' : stateLabel(assignment.status) }}</span>
      </div>

      <dl class="assignment-card__details">
        <div>
          <dt>提交截止</dt>
          <dd>{{ formatDeadline(assignment.submit_deadline) }}</dd>
        </div>
        <div>
          <dt>评审截止</dt>
          <dd>{{ formatDeadline(assignment.review_deadline) }}</dd>
        </div>
        <div>
          <dt>我的提交</dt>
          <dd>{{ submissionLabel(assignment) }}</dd>
        </div>
      </dl>

      <RouterLink
        v-if="assignment.status === 'PUBLISHED_RESULT' && assignment.type === 'FINAL_PROJECT'"
        class="action-link"
        :to="`/student/assignments/${assignment.id}/grade`"
      >
        查看最终成绩
      </RouterLink>
      <RouterLink
        v-else-if="assignment.type === 'FINAL_PROJECT'"
        class="action-link"
        :to="`/student/assignments/${assignment.id}/project-submission`"
      >
        {{ actionLabel(assignment) }}
      </RouterLink>
      <RouterLink
        v-else
        class="action-link"
        :to="`/student/assignments/${assignment.id}/programming-submission`"
      >
        {{ actionLabel(assignment) }}
      </RouterLink>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.assignment-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 24px; list-style: none; margin: 0; padding: 0; }
.assignment-card { padding: 0; border: 0; border-radius: 6px; background: var(--surface); min-width: 0; overflow: hidden; }
.assignment-card__cover { display: flex; align-items: center; justify-content: space-between; padding: 20px 26px; height: 120px; background: var(--studio-mint); color: var(--studio-dark); }
.assignment-card[data-kind=FINAL_PROJECT] .assignment-card__cover { background: var(--studio-blue); }
.assignment-card__cover > span { font-size: 20px; font-weight: 600; flex-shrink: 0; }
.assignment-card__cover svg { width: 165px; height: 100px; }
.assignment-card__body { padding: 24px; }
.assignment-card__heading { display: flex; align-items: center; gap: 14px; }
.assignment-card__title { flex: 1; min-width: 0; }
.assignment-card h2 { margin: 0; font-size: 19px; line-height: 1.5; overflow-wrap: anywhere; }
.assignment-card__details { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px; margin: 24px 0; padding: 0; border: 0; }
.assignment-card__details > div:last-child { grid-column: 1/-1; background: var(--surface-subtle); padding: 12px 14px; }
.assignment-card__details div { min-width: 0; }
dt { color: var(--muted); font-size: 12px; }
dd { margin: 5px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.action-link { display: inline-flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: 9px 14px; border: 0; border-radius: 4px; color: var(--primary-hover); background: var(--primary-soft); font-size: 14px; font-weight: 600; text-decoration: none; transition: background var(--motion-fast), color var(--motion-fast); }
.action-link:hover { background: var(--primary-soft); border-color: var(--primary); }
@media (max-width: 1050px) { .assignment-list { grid-template-columns: minmax(0,1fr); } }
@media (max-width: 680px) { .assignment-card__body { padding: 20px; } .assignment-card__cover { padding: 16px 20px; height: 100px; } .assignment-card__cover > span { font-size: 18px; } .assignment-card__cover svg { width: 140px; height: 80px; } .assignment-card__details { gap: 16px; } .assignment-card__heading { flex-wrap: wrap; gap: 12px; } .assignment-card__title { flex-basis: 100%; } }
</style>
