<script setup>
import { onMounted, ref } from 'vue'
import { getMyReviewTasks } from '../api/reviewer'

const tasks = ref([])
const error = ref('')
onMounted(async () => {
  try { tasks.value = await getMyReviewTasks() }
  catch (err) { error.value = err.message }
})
</script>

<template>
  <section class="card">
    <h1>待评审任务</h1>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="tasks.length === 0">暂无任务或接口尚未接入数据。</p>
    <ul v-else><li v-for="task in tasks" :key="task.task_id">匿名作业 {{ task.anonymous_token }}</li></ul>
  </section>
</template>
