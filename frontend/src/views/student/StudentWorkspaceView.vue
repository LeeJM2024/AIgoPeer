<script setup>
import { computed, onMounted, ref } from 'vue'

import StudentAssignmentList from '../../components/student/StudentAssignmentList.vue'
import { getMyAssignments } from '../../api/student/assignments'
import UiIcon from '../../components/UiIcon.vue'
import CourseBanner from '../../components/CourseBanner.vue'

const assignments = ref([])
const error = ref('')
const isLoading = ref(false)
const query = ref('')
const filter = ref('all')
const filters = [{ value: 'all', label: '全部作业' }, { value: 'PROGRAMMING', label: '编程练习' }, { value: 'FINAL_PROJECT', label: '期末项目' }]
const filteredAssignments = computed(() => assignments.value.filter(item =>
  (filter.value === 'all' || item.type === filter.value) && item.title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase()),
))
const submittedCount = computed(() => assignments.value.filter(item => item.submission).length)
const publishedCount = computed(() => assignments.value.filter(item => item.type === 'FINAL_PROJECT' && item.status === 'PUBLISHED_RESULT').length)

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
    <header class="page-heading">
      <div><h1>我的作业</h1><p>查看课程安排，继续你的下一次探索。</p></div>
      <button type="button" class="button button-secondary" :disabled="isLoading" @click="loadAssignments"><UiIcon name="clock" />{{ isLoading ? '正在刷新…' : '刷新作业' }}</button>
    </header>
    <CourseBanner student />
    <div v-if="isLoading" class="skeleton-grid" role="status" aria-label="正在加载作业"><span v-for="n in 3" :key="n" /></div>
    <section v-else-if="!error" class="metric-strip student-metrics" aria-label="我的学习进度">
      <div><div class="metric-top"><span>课程作业</span><UiIcon name="assignments" /></div><strong>{{ assignments.length }}<small> 份</small></strong></div>
      <div><div class="metric-top"><span>已有提交</span><UiIcon name="check" /></div><strong>{{ submittedCount }}<small> 份</small></strong></div>
      <div><div class="metric-top"><span>已发布项目成绩</span><UiIcon name="review" /></div><strong>{{ publishedCount }}<small> 份</small></strong></div>
    </section>
    <div id="assignment-workspace" class="workspace-content">
      <div class="list-tools"><div class="list-tabs" role="group" aria-label="按作业类型筛选"><button v-for="item in filters" :key="item.value" type="button" :aria-pressed="filter === item.value" @click="filter = item.value">{{ item.label }}</button></div><label class="search-field"><UiIcon name="search" /><input v-model="query" type="search" aria-label="搜索我的作业" placeholder="搜索作业名称" /></label></div>
      <p v-if="isLoading" role="status" class="muted">正在加载作业…</p>
      <div v-else-if="error" class="error" role="alert">
        <p>加载作业失败：{{ error }}</p>
        <button type="button" class="retry-button" @click="loadAssignments">重试</button>
      </div>
      <div v-else-if="assignments.length === 0" class="empty-state"><UiIcon name="book" /><h3>课程作业还在准备中</h3><p>暂无已发布作业。新注册同学请联系任课教师加入课程班级。</p></div>
      <div v-else-if="!filteredAssignments.length" class="empty-state"><UiIcon name="search" /><h3>没有找到符合条件的作业</h3><p>试试其他名称，或切换到全部作业。</p><button class="button button-secondary" type="button" @click="query = ''; filter = 'all'">显示全部作业</button></div>
      <StudentAssignmentList v-else :assignments="filteredAssignments" />
    </div>
  </section>
</template>

<style scoped>
.student-workspace { display: grid; gap: 26px; }
#assignment-workspace { scroll-margin-top: 24px; }
.list-tools { padding-block: 5px 8px; }
.student-metrics { grid-template-columns: repeat(3,minmax(0,1fr)); }
.student-metrics strong small { font-size: 12px; font-weight: 400; color: var(--muted); }
.retry-button { min-height: 40px; padding: 8px 14px; border: 1px solid var(--primary); border-radius: 7px; color: white; background: var(--primary); }
@media (max-width: 680px) { .student-workspace { gap: 20px; } .student-metrics { grid-template-columns: repeat(3,minmax(0,1fr)); } .student-metrics > div { padding: 16px 10px; border: 0; } .student-metrics :deep(.metric-top) { min-height: 40px; align-items: flex-start; font-size: 12px; } .student-metrics .ui-icon { display: none; } .student-metrics strong { font-size: 27px; } .student-metrics strong small { display: none; } }
</style>
