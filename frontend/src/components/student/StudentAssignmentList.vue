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

const assignmentTypeLabel = (type) => type === 'FINAL_PROJECT' ? '期末项目' : '编程题'

const formatDeadline = (value) => value ? dateFormatter.format(new Date(value)) : '未设置'

const submissionLabel = (assignment) => {
  if (assignment.type === 'PROGRAMMING') {
    if (!assignment.submission) return '未提交'
    return `最近一次：${codeStatusLabel(assignment.submission.status)}`
  }
  if (!assignment.submission) return '未提交'
  if (!assignment.submission.material_check_status) return `已提交（${assignment.submission.status}）`
  return `已提交（材料检查：${assignment.submission.material_check_status}）`
}

const codeStatusLabel = (status) => ({
  QUEUED: '排队中', RUNNING: '判题中', AC: '通过', WA: '答案错误',
  TLE: '超出时间限制', RE: '运行错误', CE: '编译错误', SYSTEM_ERROR: '判题异常'
}[status] ?? status)

const actionLabel = (assignment) => {
  if (assignment.type === 'FINAL_PROJECT') return assignment.submission ? '查看并重新上传' : '认领并上传'
  if (!assignment.submission) return '查看题目并提交'
  return ['QUEUED', 'RUNNING'].includes(assignment.submission.status) ? '查看判题进度' : '继续编写'
}
</script>

<template>
  <ul class="assignment-list" aria-label="我的作业列表">
    <li v-for="assignment in assignments" :key="assignment.id" class="assignment-card">
      <div class="assignment-card__heading">
        <div>
          <p class="assignment-card__eyebrow">{{ assignmentTypeLabel(assignment.type) }}</p>
          <h2>{{ assignment.title }}</h2>
        </div>
        <span class="status-badge">{{ assignment.status === 'PUBLISHED' ? '进行中' : assignment.status }}</span>
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
        v-if="assignment.type === 'FINAL_PROJECT'"
        class="action-link"
        :to="`/student/assignments/${assignment.id}/project-submission`"
      >
        认领并上传
      </RouterLink>
      <RouterLink
        v-else
        class="action-link"
        :to="`/student/assignments/${assignment.id}/programming-submission`"
      >
        {{ actionLabel(assignment) }}
      </RouterLink>
    </li>
  </ul>
</template>

<style scoped>
.assignment-list { display: grid; gap: 16px; padding: 0; margin: 24px 0 0; list-style: none; }.assignment-card { padding: 20px; border: 1px solid #cfe2d6; border-radius: 12px; background: white; box-shadow: 0 4px 12px #0b3a2a0a; }
.assignment-card__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.assignment-card h2 { margin: 4px 0 0; font-size: 18px; }
.assignment-card__eyebrow { margin: 0; color: #276749; font-size: 14px; font-weight: 700; }.status-badge { border-radius: 999px; padding: 4px 9px; color: #17603f; background: #e5f5eb; font-size: 12px; font-weight: 700; white-space: nowrap; }.assignment-card__details { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 20px 0; padding: 14px; border-radius: 8px; background: #f5faf6; }
.assignment-card__details div { min-width: 0; }
dt { color: #557262; font-size: 13px; }
dd { margin: 5px 0 0; font-size: 14px; overflow-wrap: anywhere; }
button { padding: 8px 12px; border: 0; border-radius: 6px; color: #667085; background: #eaecf0; cursor: not-allowed; }
.action-link { display: inline-block; width: fit-content; padding: 9px 13px; border-radius: 7px; color: white; background: #0d4d3a; font-weight: 700; text-decoration: none; }
@media (max-width: 680px) { .assignment-card__details { grid-template-columns: 1fr; } }
</style>
