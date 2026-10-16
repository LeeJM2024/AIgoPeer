<script setup>
import { computed, onMounted, ref } from 'vue'
import StudentAssignmentList from '../../components/student/StudentAssignmentList.vue'
import StudentAssignmentFeature from '../../components/student/StudentAssignmentFeature.vue'
import AssignmentArtwork from '../../components/AssignmentArtwork.vue'
import UiIcon from '../../components/UiIcon.vue'
import { getMyAssignments } from '../../api/student/assignments'
import {
  assignmentAction,
  assignmentDestination,
  formatDeadline,
  pendingAssignments
} from '../../presentation/assignments'
const assignments = ref([]),
  error = ref(''),
  isLoading = ref(false),
  query = ref(''),
  filter = ref('all')
const filters = [
  { value: 'all', label: '全部作业' },
  { value: 'PROGRAMMING', label: '编程练习' },
  { value: 'FINAL_PROJECT', label: '期末项目' }
]
const filteredAssignments = computed(() =>
  assignments.value.filter(
    (item) =>
      (filter.value === 'all' || item.type === filter.value) &&
      item.title
        .toLocaleLowerCase()
        .includes(query.value.trim().toLocaleLowerCase())
  )
)
const submittedCount = computed(
  () => assignments.value.filter((item) => item.submission).length
)
const publishedCount = computed(
  () =>
    assignments.value.filter(
      (item) =>
        item.type === 'FINAL_PROJECT' && item.status === 'PUBLISHED_RESULT'
    ).length
)
const pending = computed(() => pendingAssignments(assignments.value))
const featured = computed(() =>
  filter.value === 'all' && !query.value.trim()
    ? pending.value[0] || assignments.value[0]
    : null
)
const remaining = computed(() =>
  filteredAssignments.value.filter((item) => item.id !== featured.value?.id)
)
const related = computed(
  () =>
    assignments.value.find((item) => item.id !== featured.value?.id) ||
    featured.value
)
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
function resetFilters() {
  query.value = ''
  filter.value = 'all'
}
onMounted(loadAssignments)
</script>
<template>
  <section class="student-workspace">
    <header class="page-heading">
      <div>
        <h1>算法设计与分析</h1>
        <p>你的解法，在每一次实践中成形。</p>
      </div>
      <button
        class="button button-secondary"
        type="button"
        :disabled="isLoading"
        @click="loadAssignments"
      >
        <UiIcon name="clock" />{{ isLoading ? '正在刷新…' : '刷新作业' }}
      </button>
    </header>
    <div
      v-if="isLoading"
      class="skeleton-grid"
      role="status"
      aria-label="正在加载作业"
    >
      <span v-for="n in 3" :key="n" />
    </div>
    <section
      v-else-if="!error"
      class="student-metrics"
      aria-label="我的学习进度"
    >
      <span
        >课程作业 <strong>{{ assignments.length }} 份</strong></span
      ><span
        >已有提交 <strong>{{ submittedCount }} 份</strong></span
      ><span
        >已发布项目成绩 <strong>{{ publishedCount }} 份</strong></span
      >
    </section>
    <div class="learning-layout">
      <div class="learning-main">
        <StudentAssignmentFeature
          v-if="featured && !isLoading && !error"
          :assignment="featured"
        />
        <section id="assignment-workspace" aria-labelledby="works-title">
          <div class="section-heading">
            <h2 id="works-title">课程作业</h2>
            <div class="list-tabs" role="group" aria-label="按作业类型筛选">
              <button
                v-for="item in filters"
                :key="item.value"
                type="button"
                :aria-pressed="filter === item.value"
                @click="filter = item.value"
              >
                {{ item.label }}
              </button>
            </div>
          </div>
          <div class="list-tools">
            <p class="list-intro">从原理到实现，再到清晰的表达。</p>
            <label class="search-field"
              ><UiIcon name="search" /><input
                v-model="query"
                type="search"
                aria-label="搜索我的作业"
                placeholder="搜索作业名称"
            /></label>
          </div>
          <p v-if="isLoading" role="status" class="muted">正在加载作业…</p>
          <div v-else-if="error" class="notice notice-error" role="alert">
            <p>加载作业失败：{{ error }}</p>
            <button
              class="retry-button button"
              type="button"
              @click="loadAssignments"
            >
              重试
            </button>
          </div>
          <div v-else-if="!assignments.length" class="empty-state">
            <UiIcon name="book" />
            <h3>课程作业还在准备中</h3>
            <p>暂无已发布作业。新注册同学请联系任课教师加入课程班级。</p>
          </div>
          <div v-else-if="!filteredAssignments.length" class="empty-state">
            <UiIcon name="search" />
            <h3>没有找到符合条件的作业</h3>
            <p>试试其他名称，或切换到全部作业。</p>
            <button
              class="button button-secondary"
              type="button"
                @click="resetFilters"
            >
              显示全部作业
            </button>
          </div>
          <StudentAssignmentList
            v-else-if="remaining.length"
            :assignments="remaining"
          />
          <p v-else class="single-assignment-note">
            本次课程作业已在上方展开，可直接继续操作。
          </p>
        </section>
      </div>
      <aside
        v-if="!isLoading && !error"
        class="learning-aside"
        aria-label="当前事项与学习提示"
      >
        <section class="next-panel">
          <div class="section-heading">
            <h2>接下来</h2>
            <span>{{ pending.length }} 项待完成</span>
          </div>
          <RouterLink
            v-for="item in pending.slice(0, 3)"
            :key="item.id"
            class="student-todo"
            :to="assignmentDestination(item)"
            ><UiIcon :name="item.type === 'PROGRAMMING' ? 'code' : 'video'" />
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ assignmentAction(item) }}</p>
              <small>截止 {{ formatDeadline(item.submit_deadline) }}</small>
            </div></RouterLink
          >
          <p v-if="!pending.length" class="aside-note">
            当前没有待完成的提交事项，可在作业中回顾提交结果与已发布反馈。
          </p>
          <a class="aside-bottom" href="#assignment-workspace"
            >查看课程作业 <span aria-hidden="true">↓</span></a
          >
        </section>
        <section v-if="related" class="related-assignment">
          <AssignmentArtwork :assignment="related" />
          <div>
            <h2>{{ related.title }}</h2>
            <p>回到课程内容，把思路与实现联系起来。</p>
            <RouterLink :to="assignmentDestination(related)"
              >{{ assignmentAction(related) }}<UiIcon name="arrow"
            /></RouterLink>
          </div>
        </section>
        <section class="feedback-note">
          <h2>让反馈回到解法本身</h2>
          <p>
            正式发布的项目成绩与评语，会出现在对应作业中。尚未发布时，不提前展示分数。
          </p>
        </section>
      </aside>
    </div>
  </section>
</template>
<style scoped>
.student-workspace {
  display: grid;
  gap: 22px;
}
.student-metrics {
  display: flex;
  justify-content: flex-end;
  gap: 28px;
  flex-wrap: wrap;
  margin-top: -8px;
  font-size: 13px;
  color: var(--muted);
}
.student-metrics > span {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.student-metrics strong {
  font-size: 17px;
  font-weight: 650;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.learning-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 298px;
  gap: 28px;
  align-items: start;
}
.learning-main {
  display: grid;
  gap: 30px;
  min-width: 0;
}
.learning-aside {
  display: grid;
  gap: 26px;
  min-width: 0;
}
.section-heading h2 {
  font-size: 24px;
  letter-spacing: -0.5px;
}
.list-intro {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}
#assignment-workspace {
  scroll-margin-top: 24px;
}
.single-assignment-note {
  color: var(--muted);
  font-size: 14px;
  padding: 26px;
  background: var(--surface-translucent);
  border-radius: 24px;
}
.next-panel {
  background: var(--surface-translucent);
  border-radius: 28px;
  padding: 25px;
  min-height: 300px;
  display: flex;
  flex-direction: column;
}
.next-panel .section-heading {
  gap: 12px;
}
.next-panel h2 {
  font-size: 21px;
}
.next-panel .section-heading > span {
  font-size: 12px;
  color: var(--muted);
}
.student-todo {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 0 8px;
  text-decoration: none;
  color: var(--ink);
}
.student-todo > .ui-icon {
  width: 19px;
  height: 19px;
  color: var(--primary);
  margin-top: 3px;
}
.student-todo > div {
  min-width: 0;
}
.student-todo strong {
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.student-todo p,
.student-todo small {
  font-size: 12px;
  color: var(--muted);
  margin: 6px 0 0;
  line-height: 1.8;
  display: block;
}
.student-todo:hover strong {
  color: var(--primary);
}
.aside-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  text-decoration: none;
  margin-top: auto;
  padding-top: 24px;
  min-height: 44px;
}
.aside-note {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.8;
}
.related-assignment {
  border-radius: 28px;
  background: var(--art-gradient);
  overflow: hidden;
}
.related-assignment > .assignment-artwork {
  width: 100%;
  height: auto;
  aspect-ratio: 1.65;
  padding: 8px 12px 0;
}
.related-assignment > div {
  padding: 16px 24px 24px;
}
.related-assignment h2 {
  font-size: 20px;
  overflow-wrap: anywhere;
  margin: 0;
}
.related-assignment p {
  font-size: 13px;
  color: var(--muted);
  margin: 8px 0;
}
.related-assignment a {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  font-weight: 600;
  min-height: 44px;
  text-decoration: none;
}
.related-assignment a .ui-icon {
  width: 17px;
}
.feedback-note {
  padding: 0 10px;
}
.feedback-note h2 {
  font-size: 20px;
  margin-bottom: 8px;
}
.feedback-note p {
  font-size: 13px;
  line-height: 1.8;
  color: var(--muted);
  margin: 0;
}
@media (max-width: 1200px) {
  .learning-layout {
    grid-template-columns: minmax(0, 1fr) 250px;
    gap: 22px;
  }
  .next-panel {
    padding: 22px;
  }
  .student-metrics {
    gap: 20px;
  }
}
@media (max-width: 900px) {
  .learning-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .learning-aside {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .feedback-note {
    grid-column: 1/-1;
  }
  .student-metrics {
    justify-content: flex-start;
    margin: 0;
  }
}
@media (max-width: 760px) {
  .student-workspace {
    gap: 20px;
  }
  .student-metrics {
    gap: 8px 18px;
    font-size: 11px;
  }
  .student-metrics > span {
    gap: 5px;
  }
  .student-metrics strong {
    font-size: 14px;
  }
  .learning-aside {
    grid-template-columns: minmax(0, 1fr);
  }
  .learning-main {
    gap: 26px;
  }
  .learning-layout {
    gap: 26px;
  }
  .section-heading h2 {
    font-size: 23px;
  }
  .section-heading {
    gap: 12px;
  }
  .next-panel {
    min-height: 0;
  }
  .list-tools {
    gap: 14px;
  }
  .related-assignment > .assignment-artwork {
    max-height: 240px;
  }
  .feedback-note {
    padding: 0 6px;
  }
}
</style>
