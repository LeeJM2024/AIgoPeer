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
  <section class="card">
    <p class="eyebrow">学生工作台</p>
    <h1>我的作业</h1>
    <p>查看当前班级已发布作业及自己的最近一次提交状态。</p>

    <p v-if="isLoading" role="status">正在加载作业…</p>
    <div v-else-if="error" class="error" role="alert">
      <p>加载作业失败：{{ error }}</p>
      <button type="button" class="retry-button" @click="loadAssignments">重试</button>
    </div>
    <p v-else-if="assignments.length === 0" class="empty-state">暂无已发布作业。</p>
    <StudentAssignmentList v-else :assignments="assignments" />
  </section>
</template>

<style scoped>
.eyebrow { margin: 0; color: #475467; font-size: 14px; }
h1 { margin: 6px 0; }
.empty-state { margin: 24px 0 0; color: #667085; }
.retry-button { padding: 8px 12px; border: 0; border-radius: 6px; color: white; background: #12355b; cursor: pointer; }
</style>
