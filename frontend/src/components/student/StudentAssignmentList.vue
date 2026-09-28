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
  if (assignment.type === 'PROGRAMMING') return '未提交（代码提交功能将在下一迭代开放）'
  if (!assignment.submission) return '未提交'
  if (!assignment.submission.material_check_status) return `已提交（${assignment.submission.status}）`
  return `已提交（材料检查：${assignment.submission.material_check_status}）`
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
        <span class="status-badge">{{ assignment.status }}</span>
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

      <button type="button" disabled title="该功能将在下一迭代开放">下一迭代开放</button>
    </li>
  </ul>
</template>

<style scoped>
.assignment-list { display: grid; gap: 16px; padding: 0; margin: 24px 0 0; list-style: none; }
.assignment-card { padding: 20px; border: 1px solid #d9e2ef; border-radius: 8px; }
.assignment-card__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.assignment-card h2 { margin: 4px 0 0; font-size: 18px; }
.assignment-card__eyebrow { margin: 0; color: #475467; font-size: 14px; }
.status-badge { border-radius: 999px; padding: 4px 9px; color: #12355b; background: #eaf2ff; font-size: 12px; white-space: nowrap; }
.assignment-card__details { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 20px 0; }
.assignment-card__details div { min-width: 0; }
dt { color: #667085; font-size: 13px; }
dd { margin: 5px 0 0; font-size: 14px; overflow-wrap: anywhere; }
button { padding: 8px 12px; border: 0; border-radius: 6px; color: #667085; background: #eaecf0; cursor: not-allowed; }
@media (max-width: 680px) { .assignment-card__details { grid-template-columns: 1fr; } }
</style>
