<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getAiVideoStatus } from '../../api/teacher'
import UiIcon from '../../components/UiIcon.vue'
const status = ref(null)
const error = ref('')
onMounted(async () => {
  try { status.value = await getAiVideoStatus() }
  catch (err) { error.value = err.message }
})
</script>
<template>
  <div class="view-stack">
    <header class="page-heading"><h1>视频辅助评阅</h1></header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-else-if="!status" class="skeleton-page" aria-label="正在加载" />
    <section v-else class="service-state">
      <span class="service-icon"><UiIcon name="video" /></span>
      <h2>{{ status.enabled ? '视频辅助评阅已开启' : '视频辅助评阅暂未开启' }}</h2>
      <p>{{ status.enabled ? '可在作业评分页查看视频材料。辅助评阅以管理员开放的功能为准。' : '你仍可以在作业评分页观看视频、填写评分。' }}</p>
      <RouterLink class="button" to="/teacher/assignments">查看作业<UiIcon name="arrow" /></RouterLink>
      <small v-if="!status.enabled">如需使用辅助评阅，请联系课程管理员。</small>
    </section>
  </div>
</template>
