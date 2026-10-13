<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getAssignments, getDashboard } from '../../api/teacher'
import UiIcon from '../../components/UiIcon.vue'

const stats = ref(null)
const assignments = ref([])
const error = ref('')
onMounted(async () => {
  try { [stats.value, assignments.value] = await Promise.all([getDashboard(), getAssignments()]) }
  catch (err) { error.value = err.message }
})
const stateName = { DRAFT: '草稿', PUBLISHED: '已发布', SUBMITTING: '提交中', REVIEWER_INITIALIZING: '分配评审中', REVIEWER_GRADING: '评审中', AGGREGATING: '汇总评审中', TEACHER_GRADING: '教师评分', PUBLISHED_RESULT: '成绩已发布' }
</script>

<template>
  <div class="view-stack">
    <header class="page-heading"><h1>课程总览</h1><RouterLink class="button" to="/teacher/assignments">管理作业<UiIcon name="arrow" /></RouterLink></header>
    <p v-if="error" class="notice notice-error" role="alert">加载失败：{{ error }}</p>
    <div v-else-if="!stats" class="skeleton-grid" aria-label="正在加载"><span v-for="n in 4" :key="n" /></div>
    <section v-else class="metric-strip" aria-label="课程关键状态">
      <div><strong>{{ stats.active_assignments }}</strong><span>进行中作业</span></div>
      <div><strong>{{ stats.awaiting_grading }}</strong><span>待评分</span></div>
      <div><strong>{{ stats.pending_tasks }}</strong><span>待完成评审</span></div>
      <div :class="{ attention: stats.open_anomalies > 0 }"><strong>{{ stats.open_anomalies }}</strong><span>待复核</span></div>
    </section>
    <section class="data-section">
      <div class="section-heading"><h2>最近作业</h2><RouterLink to="/teacher/assignments">查看全部</RouterLink></div>
      <div v-if="assignments.length" class="assignment-list">
        <RouterLink v-for="item in assignments.slice(0, 5)" :key="item.id" :to="`/teacher/assignments/${item.id}`" class="assignment-row">
          <div><strong>{{ item.title }}</strong><span>{{ item.type === 'FINAL_PROJECT' ? '期末项目' : '编程题' }}</span></div>
          <div class="row-numbers"><span>{{ item.submission_count }} 份提交</span><span>{{ item.review_task_count }} 条评审任务</span></div>
          <span class="status-chip">{{ stateName[item.status] || '状态待更新' }}</span>
          <UiIcon name="arrow" />
        </RouterLink>
      </div>
      <div v-else class="empty-state"><h3>还没有作业</h3><p>创建作业后，可在这里查看学生的提交进度。</p><RouterLink class="button" to="/teacher/assignments">创建第一份作业</RouterLink></div>
    </section>
  </div>
</template>
