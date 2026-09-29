<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getAssignments, getDashboard } from '../../api/teacher'

const stats = ref(null)
const assignments = ref([])
const error = ref('')
onMounted(async () => {
  try { [stats.value, assignments.value] = await Promise.all([getDashboard(), getAssignments()]) }
  catch (err) { error.value = err.message }
})
const stateName = { DRAFT: '草稿', PUBLISHED: '已发布', SUBMITTING: '提交中', REVIEWER_GRADING: '评审中', AGGREGATING: '聚合中', TEACHER_GRADING: '教师评分', PUBLISHED_RESULT: '成绩已发布' }
</script>

<template>
  <div class="view-stack">
    <header class="page-heading"><div><p class="section-label">今日工作</p><h1>课程总览</h1><p>从未完成的环节继续，所有发布动作都需要明确确认。</p></div><RouterLink class="button" to="/teacher/assignments">管理作业</RouterLink></header>
    <p v-if="error" class="notice notice-error" role="alert">加载失败：{{ error }}</p>
    <div v-else-if="!stats" class="skeleton-grid" aria-label="正在加载"><span v-for="n in 4" :key="n" /></div>
    <section v-else class="metric-strip" aria-label="课程关键状态">
      <div><strong>{{ stats.active_assignments }}</strong><span>进行中作业</span></div>
      <div><strong>{{ stats.awaiting_grading }}</strong><span>等待教师评分</span></div>
      <div><strong>{{ stats.pending_tasks }}</strong><span>未完成评审任务</span></div>
      <div :class="{ attention: stats.open_anomalies > 0 }"><strong>{{ stats.open_anomalies }}</strong><span>待复核异常</span></div>
    </section>
    <section class="data-section">
      <div class="section-heading"><div><h2>最近作业</h2><p>状态决定当前允许执行的操作。</p></div><RouterLink to="/teacher/assignments">查看全部</RouterLink></div>
      <div v-if="assignments.length" class="assignment-list">
        <RouterLink v-for="item in assignments.slice(0, 5)" :key="item.id" :to="`/teacher/assignments/${item.id}`" class="assignment-row">
          <div><strong>{{ item.title }}</strong><span>{{ item.type === 'FINAL_PROJECT' ? '期末项目' : '编程题' }}</span></div>
          <div class="row-numbers"><span>{{ item.submission_count }} 份提交</span><span>{{ item.review_task_count }} 条评审任务</span></div>
          <span class="status-chip">{{ stateName[item.status] || item.status }}</span>
        </RouterLink>
      </div>
      <div v-else class="empty-state"><h3>还没有作业</h3><p>先创建一份作业和评分量表，再配置两组跨班评审人。</p><RouterLink class="button" to="/teacher/assignments">创建第一份作业</RouterLink></div>
    </section>
  </div>
</template>
