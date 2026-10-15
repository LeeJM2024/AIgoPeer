<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getAssignments, getDashboard } from '../../api/teacher'
import UiIcon from '../../components/UiIcon.vue'
import CourseBanner from '../../components/CourseBanner.vue'

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
const reviewAssignments = computed(() => assignments.value.filter(item => ['REVIEWER_INITIALIZING', 'REVIEWER_GRADING', 'AGGREGATING'].includes(item.status)))
const gradingAssignments = computed(() => assignments.value.filter(item => item.status === 'TEACHER_GRADING'))
const steps = [
  { icon: 'assignments', title: '发布课程作业', detail: '设置作业要求、截止时间与评分量表。' },
  { icon: 'people', title: '组织课程评审', detail: '按课程规则分配任务，跟进材料与评阅进度。' },
  { icon: 'review', title: '评分与异常复核', detail: '结合原始材料与评审证据，完成教师评分。' },
  { icon: 'check', title: '确认并发布成绩', detail: '满足发布条件后，学生可查看本人反馈。' },
]
const stateName = { DRAFT: '草稿', PUBLISHED: '已发布', SUBMITTING: '提交中', REVIEWER_INITIALIZING: '分配评审中', REVIEWER_GRADING: '评审中', AGGREGATING: '汇总评审中', TEACHER_GRADING: '教师评分', PUBLISHED_RESULT: '成绩已发布' }
</script>

<template>
  <div class="view-stack">
    <header class="page-heading"><div><h1>课程总览</h1><p>掌握课程进度，从待处理的事项开始。</p></div><RouterLink class="button" to="/teacher/assignments"><UiIcon name="assignments" />管理作业</RouterLink></header>
    <CourseBanner />
    <div v-if="error" class="notice notice-error" role="alert">加载失败：{{ error }} <button type="button" class="text-button" @click="load">重新加载</button></div>
    <div v-else-if="loading" class="skeleton-grid" aria-label="正在加载"><span v-for="n in 4" :key="n" /></div>
    <section v-else class="metric-strip" aria-label="课程关键状态">
      <div><div class="metric-top"><span>进行中作业</span><UiIcon name="assignments" /></div><strong>{{ stats.active_assignments }}</strong><small>关注当前课程安排</small></div>
      <div><div class="metric-top"><span>待评分</span><UiIcon name="review" /></div><strong>{{ stats.awaiting_grading }}</strong><small>等待教师完成评分</small></div>
      <div><div class="metric-top"><span>待完成评审</span><UiIcon name="clock" /></div><strong>{{ stats.pending_tasks }}</strong><small>跨班评审任务进度</small></div>
      <div :class="{ attention: stats.open_anomalies > 0 }"><div class="metric-top"><span>待复核</span><UiIcon name="shield" /></div><strong>{{ stats.open_anomalies }}</strong><small>需要教师查看证据</small></div>
    </section>
    <div v-if="stats && !loading && !error" class="dashboard-columns">
    <div class="dashboard-main">
    <section class="data-section">
      <div class="section-heading"><div><h2>最近作业</h2><p>查看提交情况，继续管理作业流程。</p></div><RouterLink to="/teacher/assignments">全部作业<UiIcon name="arrow" /></RouterLink></div>
      <div v-if="assignments.length" class="assignment-list">
        <RouterLink v-for="item in assignments.slice(0, 5)" :key="item.id" :to="`/teacher/assignments/${item.id}`" class="assignment-row">
          <div class="dashboard-assignment"><span class="assignment-symbol" :data-kind="item.type"><UiIcon :name="item.type === 'FINAL_PROJECT' ? 'book' : 'code'" /></span><div><strong>{{ item.title }}</strong><small>{{ item.type === 'FINAL_PROJECT' ? '期末项目' : '编程题' }} · {{ item.submission_count }} 份提交</small></div></div>
          <span class="status-chip" :data-state="item.status">{{ stateName[item.status] || '状态待更新' }}</span>
          <UiIcon name="arrow" />
        </RouterLink>
      </div>
      <div v-else class="empty-state"><h3>还没有作业</h3><p>创建作业后，可在这里查看学生的提交进度。</p><RouterLink class="button" to="/teacher/assignments">创建第一份作业</RouterLink></div>
    </section>
    <section class="data-section follow-up-section">
      <div class="section-heading"><div><h2>接下来处理</h2><p>根据当前作业阶段，继续推进课程。</p></div><UiIcon name="clock" /></div>
      <div v-if="!reviewAssignments.length && !gradingAssignments.length && !stats.open_anomalies" class="dashboard-clear"><UiIcon name="check" /><div><strong>当前没有评审或评分阶段的待办</strong><p>可前往作业列表，查看提交进度或创建下一份作业。</p></div></div>
      <RouterLink v-for="item in gradingAssignments" :key="`grade-${item.id}`" class="next-task" :to="`/teacher/assignments/${item.id}/grading`"><span class="task-icon"><UiIcon name="review" /></span><div><strong>完成教师评分</strong><small>{{ item.title }}</small></div><UiIcon name="arrow" /></RouterLink>
      <RouterLink v-for="item in reviewAssignments" :key="item.id" class="next-task" :to="`/teacher/assignments/${item.id}/reviews`"><span class="task-icon"><UiIcon name="people" /></span><div><strong>跟进跨班评审</strong><small>{{ item.title }} · {{ stateName[item.status] }}</small></div><UiIcon name="arrow" /></RouterLink>
      <RouterLink v-if="stats.open_anomalies" class="next-task" to="/teacher/assignments"><span class="task-icon"><UiIcon name="shield" /></span><div><strong>{{ stats.open_anomalies }} 项异常待复核</strong><small>从对应作业进入评审与复核页，查看证据。</small></div><UiIcon name="arrow" /></RouterLink>
    </section>
    </div>
    <aside class="course-guide data-section" aria-labelledby="course-guide-title"><h2 id="course-guide-title">课程路径</h2><ol><li v-for="step in steps" :key="step.title"><span class="guide-number"><UiIcon :name="step.icon" /></span><div><h3>{{ step.title }}</h3><p>{{ step.detail }}</p></div></li></ol><div class="guide-note"><UiIcon name="shield" /><p>教师评分独立保留，异常结果由教师复核后确认。</p></div></aside>
    </div>
  </div>
</template>

<style scoped>
.dashboard-columns { display: grid; grid-template-columns: minmax(0,1fr) 268px; gap: 24px; align-items: start; }
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
.follow-up-section { background: var(--primary-soft); }
.dashboard-clear { display: flex; align-items: flex-start; gap: 12px; padding: 10px 0; }
.dashboard-clear > .ui-icon { color: var(--success); }
.dashboard-clear strong { font-size: 13px; font-weight: 550; }
.dashboard-clear p { color: var(--muted); font-size: 12px; margin: 4px 0 0; }
@media (max-width: 1200px) { .dashboard-columns { grid-template-columns: minmax(0,1fr); } .course-guide ol { grid-template-columns: repeat(2,minmax(0,1fr)); } .guide-note { margin-top: 22px; } }
@media (max-width: 680px) { .dashboard-main .assignment-row { grid-template-columns: minmax(0,1fr) auto; } .dashboard-assignment { gap: 10px; } .assignment-symbol { display: none; } .dashboard-main .assignment-row .status-chip { grid-row: auto; } .course-guide ol { grid-template-columns: minmax(0,1fr); } }
</style>
