<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getAssignments, getDashboard } from '../../api/teacher'
import UiIcon from '../../components/UiIcon.vue'
import AssignmentArtwork from '../../components/AssignmentArtwork.vue'
import { assignmentTypeLabel } from '../../presentation/assignments'

const stats = ref(null)
const assignments = ref([])
const error = ref('')
const loading = ref(true)
async function load() {
  loading.value = true
  error.value = ''
  try { [stats.value, assignments.value] = await Promise.all([getDashboard(), getAssignments()]) }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
onMounted(load)
const reviewAssignments = computed(() => assignments.value.filter(item => item.type === 'FINAL_PROJECT' && ['REVIEWER_INITIALIZING', 'REVIEWER_GRADING', 'AGGREGATING'].includes(item.status)))
const gradingAssignments = computed(() => assignments.value.filter(item => item.type === 'FINAL_PROJECT' && item.status === 'TEACHER_GRADING'))
const focusAssignment = computed(() => gradingAssignments.value[0] || reviewAssignments.value[0] || assignments.value[0])
const stateName = { DRAFT: '草稿', PUBLISHED: '已发布', SUBMITTING: '提交中', REVIEWER_INITIALIZING: '分配评审中', REVIEWER_GRADING: '评审中', AGGREGATING: '汇总评审中', TEACHER_GRADING: '教师评分', PUBLISHED_RESULT: '成绩已发布' }
</script>

<template>
  <div class="view-stack">
    <header class="page-heading"><div><h1>课程总览</h1><p>掌握课程进度，从待处理的事项开始。</p></div><RouterLink class="button" to="/teacher/assignments"><UiIcon name="assignments" />管理作业</RouterLink></header>
    <div v-if="error" class="notice notice-error" role="alert">加载失败：{{ error }} <button type="button" class="text-button" @click="load">重新加载</button></div>
    <div v-else-if="loading" class="skeleton-grid" aria-label="正在加载"><span v-for="n in 4" :key="n" /></div>
    <section v-else class="metric-strip" aria-label="课程关键状态">
      <div><div class="metric-top"><span>进行中作业</span><UiIcon name="assignments" /></div><strong>{{ stats.active_assignments }}</strong><small>关注当前课程安排</small></div>
      <div><div class="metric-top"><span>待评分</span><UiIcon name="review" /></div><strong>{{ stats.awaiting_grading }}</strong><small>等待教师完成评分</small></div>
      <div><div class="metric-top"><span>待完成评审</span><UiIcon name="clock" /></div><strong>{{ stats.pending_tasks }}</strong><small>跨班评审任务进度</small></div>
      <div :class="{ attention: stats.open_anomalies > 0 }"><div class="metric-top"><span>待复核</span><UiIcon name="shield" /></div><strong>{{ stats.open_anomalies }}</strong><small>需要教师查看证据</small></div>
    </section>
    <div v-if="stats && !loading && !error" class="dashboard-columns" :class="{ 'has-focus': focusAssignment }">
    <div class="dashboard-main">
    <section class="data-section follow-up-section">
      <div class="section-heading"><div><h2>接下来处理</h2><p>根据当前作业阶段，继续推进课程。</p></div><UiIcon name="clock" /></div>
      <div v-if="!reviewAssignments.length && !gradingAssignments.length && !stats.open_anomalies" class="dashboard-clear"><UiIcon name="check" /><div><strong>当前没有评审或评分阶段的待办</strong><p>可前往作业列表，查看提交进度或创建下一份作业。</p></div></div>
      <RouterLink v-for="item in gradingAssignments" :key="`grade-${item.id}`" class="next-task" :to="`/teacher/assignments/${item.id}/grading`"><span class="task-icon"><UiIcon name="review" /></span><div><strong>完成教师评分</strong><small>{{ item.title }}</small></div><UiIcon name="arrow" /></RouterLink>
      <RouterLink v-for="item in reviewAssignments" :key="item.id" class="next-task" :to="`/teacher/assignments/${item.id}/reviews`"><span class="task-icon"><UiIcon name="people" /></span><div><strong>跟进跨班评审</strong><small>{{ item.title }} · {{ stateName[item.status] }}</small></div><UiIcon name="arrow" /></RouterLink>
      <RouterLink v-if="stats.open_anomalies" class="next-task" to="/teacher/assignments"><span class="task-icon"><UiIcon name="shield" /></span><div><strong>{{ stats.open_anomalies }} 项异常待复核</strong><small>从对应作业进入评审与复核页，查看证据。</small></div><UiIcon name="arrow" /></RouterLink>
    </section>
    <section class="data-section">
      <div class="section-heading"><div><h2>最近作业</h2><p>查看提交情况，继续管理作业流程。</p></div><RouterLink to="/teacher/assignments">全部作业<UiIcon name="arrow" /></RouterLink></div>
      <div v-if="assignments.length" class="assignment-list">
        <RouterLink v-for="item in assignments.slice(0, 5)" :key="item.id" :to="`/teacher/assignments/${item.id}`" class="assignment-row">
          <div class="dashboard-assignment"><span class="assignment-cover"><AssignmentArtwork :assignment="item" /></span><div><strong>{{ item.title }}</strong><small>{{ assignmentTypeLabel(item.type) }} · {{ item.submission_count }} 份提交</small></div></div>
          <span class="status-chip" :data-state="item.status">{{ stateName[item.status] || '状态待更新' }}</span>
          <UiIcon name="arrow" />
        </RouterLink>
      </div>
      <div v-else class="empty-state"><h3>还没有作业</h3><p>创建作业后，可在这里查看学生的提交进度。</p><RouterLink class="button" to="/teacher/assignments">创建第一份作业</RouterLink></div>
    </section>
    </div>
    <aside v-if="focusAssignment" class="course-focus" aria-labelledby="course-focus-title">
      <div class="focus-art"><AssignmentArtwork :assignment="focusAssignment" /></div>
      <div class="focus-copy"><p>课程进行时</p><h2 id="course-focus-title">{{ focusAssignment.title }}</h2><span>{{ stateName[focusAssignment.status] || '状态待更新' }} · {{ focusAssignment.submission_count }} 份提交</span><RouterLink :to="`/teacher/assignments/${focusAssignment.id}`">查看作业详情 <UiIcon name="arrow" /></RouterLink><small>算法主题插画，非题目测试数据</small></div>
    </aside>
    </div>
  </div>
</template>

<style scoped>
.dashboard-columns { display: grid; grid-template-columns: minmax(0,1fr); gap: 24px; align-items: start; }
.dashboard-columns.has-focus { grid-template-columns: minmax(0,1fr) 330px; }
.dashboard-main { display: grid; gap: 24px; min-width: 0; }
.dashboard-main .assignment-row { grid-template-columns: minmax(0,1fr) auto 18px; gap: 12px; }
.assignment-row > .dashboard-assignment { display: flex; align-items: center; gap: 12px; }
.dashboard-assignment > div { display: grid; gap: 5px; min-width: 0; }
.dashboard-assignment strong { font-size: 15px; }
.dashboard-assignment small { font-size: 13px; color: var(--muted); }
.assignment-symbol, .task-icon { display: grid; place-items: center; width: 44px; height: 48px; border-radius: 4px; color: var(--primary); background: var(--primary-soft); flex-shrink: 0; }
.assignment-symbol[data-kind=FINAL_PROJECT] { background: var(--studio-blue); color: var(--ink); }
.assignment-symbol .ui-icon { width: 18px; }
.next-task { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--ink); padding: 16px 0; border-top: 1px solid var(--border); }
.next-task > div { display: grid; gap: 3px; flex: 1; min-width: 0; }
.next-task strong { font-size: 15px; font-weight: 600; }
.next-task small { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.next-task > .ui-icon { width: 16px; color: var(--muted); }
.next-task:hover strong { color: var(--primary); }
.task-icon { width: 34px; height: 34px; background: var(--surface-subtle); }
.task-icon .ui-icon { width: 17px; }
.course-guide { padding: 26px 22px; background: var(--studio-blue); }
.course-guide > h2 { font-size: 20px; margin: 0 0 28px; }
.course-guide ol { display: grid; gap: 24px; padding: 0; margin: 0; list-style: none; }
.course-guide li { display: flex; gap: 12px; }
.guide-number { color: var(--ink); background: var(--surface); width: 32px; height: 36px; border-radius: 4px; display: grid; place-items: center; flex-shrink: 0; }
.guide-number .ui-icon { width: 17px; height: 17px; }
.course-guide h3 { font-size: 14px; margin: 2px 0 5px; font-weight: 600; }
.course-guide li p { color: var(--muted); font-size: 13px; margin: 0; line-height: 1.8; }
.guide-note { margin-top: 28px; border-top: 0; padding-top: 8px; display: flex; gap: 9px; color: var(--muted); }
.guide-note .ui-icon { width: 16px; color: var(--primary); margin-top: 2px; }
.guide-note p { margin: 0; font-size: 13px; line-height: 1.8; }
.follow-up-section { background: var(--surface-translucent); order: -1; }
.assignment-cover { width: 88px; height: 64px; flex: none; overflow: hidden; border-radius: 16px; background: var(--art-gradient); }
.assignment-cover :deep(svg) { width: 100%; height: 100%; }
.course-focus { overflow: hidden; border-radius: 32px 80px 32px 32px; background: var(--feature-gradient); color: white; }
.focus-art { background: var(--art-gradient); border-radius: 0 0 72px 0; }
.focus-art :deep(svg) { width: 100%; display: block; }
.focus-copy { display: grid; gap: 16px; padding: 28px; }
.focus-copy p { margin: 0; color: #c9dcff; font-size: 13px; }
.focus-copy h2 { margin: 0; font-size: 25px; line-height: 1.5; overflow-wrap: anywhere; color: white; }
.focus-copy span { font-size: 13px; color: #d9e6fc; }
.focus-copy a { color: white; display: inline-flex; align-items: center; gap: 8px; min-height: 44px; }
.focus-copy small { font-size: 12px; color: #c9dcff; }
.dashboard-clear { display: flex; align-items: flex-start; gap: 12px; padding: 10px 0; }
.dashboard-clear > .ui-icon { color: var(--success); }
.dashboard-clear strong { font-size: 13px; font-weight: 550; }
.dashboard-clear p { color: var(--muted); font-size: 12px; margin: 4px 0 0; }
@media (max-width: 1000px) { .dashboard-columns.has-focus { grid-template-columns: minmax(0,1fr); } .course-focus { display: grid; grid-template-columns: 1fr 1fr; } }
@media (max-width: 580px) { .course-focus { grid-template-columns: 1fr; } .assignment-cover { width: 64px; height: 56px; } }
@media (max-width: 680px) { .dashboard-main .assignment-row { grid-template-columns: minmax(0,1fr) auto; } .dashboard-assignment { gap: 10px; } .assignment-symbol { display: none; } .dashboard-main .assignment-row .status-chip { grid-row: auto; } .course-guide ol { grid-template-columns: minmax(0,1fr); } }
</style>
