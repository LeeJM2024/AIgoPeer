<script setup>
import { onMounted, ref } from 'vue'

import StudentAssignmentList from '../../components/student/StudentAssignmentList.vue'
import { getMyAssignments } from '../../api/student/assignments'

const assignments = ref([])
const error = ref('')
const isLoading = ref(false)

async function loadAssignments() {
  isLoading.value = true
  error.value = ''
  try {
    assignments.value = await getMyAssignments()
  } catch (err) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}

onMounted(loadAssignments)
</script>

<template>
  <section class="student-workspace">
    <header class="workspace-hero">
      <p class="eyebrow">学生工作台</p>
      <h1>我的作业</h1>
      <p>从这里开始：查看作业要求、继续编写，或确认最近一次提交状态。</p>
    </header>

    <div class="workspace-content">
      <p v-if="isLoading" role="status">正在加载作业…</p>
      <div v-else-if="error" class="error" role="alert">
        <p>加载作业失败：{{ error }}</p>
        <button type="button" class="retry-button" @click="loadAssignments">重试</button>
      </div>
      <p v-else-if="assignments.length === 0" class="empty-state">暂无已发布作业。</p>
      <StudentAssignmentList v-else :assignments="assignments" />
    </div>
  </section>
</template>

<style scoped>
.student-workspace { overflow: hidden; border: 1px solid #317158; border-radius: 16px; background: #f7fbf8; box-shadow: 0 16px 36px #011a1238; }
.workspace-hero { padding: 30px; color: #edf9f1; background: linear-gradient(120deg, #063a2b, #0d5a42); }.workspace-hero h1 { margin: 7px 0; font-size: clamp(28px, 4vw, 36px); }.workspace-hero > p:last-child { max-width: 610px; margin: 0; color: #c9e6d4; line-height: 1.6; }.workspace-content { padding: 4px 28px 28px; }.eyebrow { margin: 0; color: #9bd0af; font-size: 14px; font-weight: 700; }
.empty-state { margin: 24px 0 0; color: #667085; }
.retry-button { padding: 8px 12px; border: 0; border-radius: 6px; color: white; background: #0d4d3a; cursor: pointer; }
@media (max-width: 600px) { .workspace-hero, .workspace-content { padding-left: 18px; padding-right: 18px; } }
</style>
