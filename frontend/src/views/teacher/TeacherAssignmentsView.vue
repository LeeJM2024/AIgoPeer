<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import UiIcon from '../../components/UiIcon.vue'
import AssignmentArtwork from '../../components/AssignmentArtwork.vue'
import ProgrammingProblemEditor from '../../components/teacher/ProgrammingProblemEditor.vue'
import { assignmentTypeLabel, subjectiveTypes } from '../../presentation/assignments'
import {
  createAssignment,
  getAssignments,
  getClasses,
  getAssignment,
  editAssignment,
  deleteAssignment,
  closeAssignment,
  reopenAssignment,
  getTopics,
} from '../../api/teacher'

const editingId = ref(null)
const notice = ref('')
const assignments = ref([])
const classes = ref([])
const topics = ref([])
const query = ref('')
const filter = ref('all')
const filters = [
  { value: 'all', label: '全部作业' },
  { value: 'ongoing', label: '进行中' },
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '成绩已发布' },
  { value: 'closed', label: '已关闭' },
]
const filteredAssignments = computed(() => assignments.value.filter((item) => {
  const matchesText = item.title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())
  const matchesStatus = filter.value === 'all' ||
    (filter.value === 'draft' && item.status === 'DRAFT') ||
    (filter.value === 'published' && item.status === 'PUBLISHED_RESULT') ||
    (filter.value === 'ongoing' && !item.closed_at && !['DRAFT', 'PUBLISHED_RESULT'].includes(item.status)) ||
    (filter.value === 'closed' && item.closed_at)
  return matchesText && matchesStatus
}))
const showForm = ref(false)
const error = ref('')
const busy = ref(false)
const blankProblem = () => ({
  statement: '',
  input_description: '',
  output_description: '',
  time_limit_ms: 2000,
  memory_limit_mb: 256,
  test_cases: [
    { input_data: '', expected_output: '', is_public: true },
    { input_data: '', expected_output: '', is_public: false },
  ],
})
const stateName = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
  SUBMITTING: '提交中',
  REVIEWER_INITIALIZING: '分配评审中',
  REVIEWER_GRADING: '跨班评审中',
  AGGREGATING: '汇总评审中',
  TEACHER_GRADING: '教师评分中',
  PUBLISHED_RESULT: '成绩已发布',
}
const form = reactive({
  title: '',
  type: 'FINAL_PROJECT',
  statement: '',
  topic_ids: [],
  programming_problem: blankProblem(),
  class_ids: [],
  submit_deadline: '',
  review_deadline: '',
  teacher_weight: 0.6,
  designated_review_weight: 0.4,
  rubric_items: [
    {
      name: '原理讲解',
      max_score: 30,
      sort_order: 1,
      description: '概念、步骤和复杂度准确完整',
    },
    {
      name: '例题与实现',
      max_score: 35,
      sort_order: 2,
      description: '例题推演与代码实现一致',
    },
    {
      name: '材料完整性',
      max_score: 20,
      sort_order: 3,
      description: 'PPT、视频、代码、测试与 README 完整',
    },
    {
      name: '表达与规范',
      max_score: 15,
      sort_order: 4,
      description: '结构清晰，引用与格式规范',
    },
  ],
})
const defaultRubric = form.rubric_items.map((item) => ({ ...item }))
const teacherWeightPercent = computed({
  get: () => Math.round(form.teacher_weight * 10000) / 100,
  set: (value) => { form.teacher_weight = value === '' ? NaN : Number((Number(value) / 100).toFixed(4)) },
})
const reviewWeightPercent = computed({
  get: () => Math.round(form.designated_review_weight * 10000) / 100,
  set: (value) => { form.designated_review_weight = value === '' ? NaN : Number((Number(value) / 100).toFixed(4)) },
})
const weightError = computed(() => {
  if (form.type !== 'FINAL_PROJECT') return ''
  const weights = [form.teacher_weight, form.designated_review_weight]
  if (weights.some(value => !Number.isFinite(value) || value < 0 || value > 1)) {
    return '请填写 0%～100% 之间的评分比例。'
  }
  if (Math.abs(weights[0] + weights[1] - 1) > 1e-9) {
    return '教师评分与同伴评审比例合计必须为 100%。'
  }
  return ''
})

async function load() {
  try {
    ;[assignments.value, classes.value] = await Promise.all([
      getAssignments(),
      getClasses(),
    ])
    topics.value = await getTopics()
  } catch (err) {
    error.value = err.message
  }
}
onMounted(load)
function addRubric() {
  form.rubric_items.push({
    name: '',
    max_score: 10,
    sort_order: form.rubric_items.length + 1,
    description: '',
  })
}
function changeType() {
  if (form.type === 'FINAL_PROJECT') {
    form.class_ids = form.class_ids.slice(0, 2)
    form.rubric_items = defaultRubric.map((item) => ({ ...item }))
  }
}
function removeRubric(index) {
  form.rubric_items.splice(index, 1)
  form.rubric_items.forEach((item, i) => (item.sort_order = i + 1))
}
function localTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}
function newDraft() {
  if (busy.value) return
  editingId.value = null
  form.title = ''
  form.type = 'FINAL_PROJECT'
  form.statement = ''
  form.topic_ids = []
  form.programming_problem = blankProblem()
  form.class_ids = []
  form.submit_deadline = ''
  form.review_deadline = ''
  form.teacher_weight = 0.6
  form.designated_review_weight = 0.4
  form.rubric_items = defaultRubric.map((item) => ({ ...item }))
  delete form.expected_updated_at
  showForm.value = !showForm.value
  error.value = ''
  notice.value = ''
}
async function edit(item) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const detail = await getAssignment(item.id)
    Object.assign(form, {
      expected_updated_at: detail.updated_at,
      title: detail.title,
      type: detail.type,
      statement: detail.statement || '',
      topic_ids: (detail.topics || []).map((t) => t.id),
      programming_problem: detail.programming_problem || blankProblem(),
      class_ids: detail.classes.map((c) => c.id),
      submit_deadline: localTime(detail.submit_deadline),
      review_deadline: localTime(detail.review_deadline),
      teacher_weight: Number(detail.teacher_weight),
      designated_review_weight: Number(detail.designated_review_weight),
      rubric_items: detail.rubric_items.map((r) => ({
        name: r.name,
        max_score: Number(r.max_score),
        sort_order: r.sort_order,
        description: r.description || '',
      })),
    })
    editingId.value = item.id
    showForm.value = true
    window.scrollTo({ top: 0, behavior: 'auto' })
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function remove(item) {
  if (!confirm(`删除作业“${item.title}”？删除后将从教师与学生入口移除，现有链接不可继续访问。`))
    return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await deleteAssignment(item.id)
    if (editingId.value === item.id) showForm.value = false
    await load()
    notice.value = '作业已删除。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function submit() {
  error.value = ''
  if (!form.class_ids.length || (form.type === 'FINAL_PROJECT' && form.class_ids.length !== 2)) {
    error.value = form.type === 'FINAL_PROJECT' ? '期末微课作业必须选择两个班级。' : '请至少选择一个班级。'
    return
  }
  if (weightError.value) {
    error.value = weightError.value
    return
  }
  busy.value = true
  try {
    const payload = {
      ...form,
      submit_deadline: new Date(form.submit_deadline).toISOString(),
      review_deadline:
        form.type === 'FINAL_PROJECT' ? new Date(form.review_deadline).toISOString() : null,
      programming_problem:
        form.type === 'PROGRAMMING' ? form.programming_problem : null,
      teacher_weight: form.type === 'FINAL_PROJECT' ? form.teacher_weight : 1,
      designated_review_weight: form.type === 'FINAL_PROJECT' ? form.designated_review_weight : 0,
      rubric_items:
        form.type === 'PROGRAMMING'
          ? [{ name: '编程题', max_score: 100, sort_order: 1 }]
          : form.type === 'FINAL_PROJECT' ? form.rubric_items : [],
    }
    const result = editingId.value
      ? await editAssignment(editingId.value, payload)
      : await createAssignment(payload)
    notice.value = result.panels_reset
      ? '草稿已保存，适用班级与作业类型已更新。'
      : '草稿已保存。'
    showForm.value = false
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function toggleClosed(item) {
  if (!confirm(item.closed_at ? `恢复作业“${item.title}”？按原有阶段与截止时间继续。` : `关闭作业“${item.title}”？学生提交和评审将暂停，可稍后恢复。`)) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await (item.closed_at ? reopenAssignment(item.id) : closeAssignment(item.id))
    await load()
    notice.value = item.closed_at ? '作业已恢复。' : '作业已关闭。'
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="view-stack">
    <header class="page-heading">
      <div>
        <h1>作业与评分</h1>
      </div>
      <button class="button" :disabled="busy" @click="newDraft">
        {{ showForm ? '收起表单' : '新建作业' }}
      </button>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <form v-if="showForm" class="editor-panel" @submit.prevent="submit">
      <div class="section-heading">
        <div>
          <h2>{{ editingId ? '编辑草稿' : '新建作业' }}</h2>
          <p>
            保存为草稿，发布前可以修改。
          </p>
        </div>
      </div>
      <fieldset class="bare-fieldset" :disabled="busy">
        <div class="form-grid">
          <label
            >作业类型<select v-model="form.type" aria-label="作业类型" @change="changeType">
              <option value="FINAL_PROJECT">期末微课作业</option>
              <option value="PROGRAMMING">编程作业（C++17 自动测评）</option>
              <option value="ALGORITHM_ANALYSIS">算法分析题（在线作答）</option>
              <option value="PROOF">证明题（在线作答）</option>
              <option value="OPEN_ENDED">开放问答题（在线作答）</option>
            </select></label
          ><label class="span-2"
            >作业名称<input v-model="form.title" required maxlength="200"
          /></label>
          <label
            >提交截止时间<input
              v-model="form.submit_deadline"
              type="datetime-local"
              required
          /></label>
          <label v-if="form.type === 'FINAL_PROJECT'"
            >评审截止时间<input
              v-model="form.review_deadline"
              type="datetime-local"
              required
          /></label>
          <fieldset class="span-2" aria-label="适用班级">
            <legend>适用班级（{{ form.type === 'FINAL_PROJECT' ? '必须选择两个' : '至少选择一个，可多选' }}）</legend>
            <label v-for="item in classes" :key="item.id" class="check-row"
              ><input
                v-model="form.class_ids"
                type="checkbox"
                :value="item.id"
                :disabled="
                  form.type === 'FINAL_PROJECT' && form.class_ids.length >= 2 &&
                  !form.class_ids.includes(item.id)
                "
              />{{ item.name }}
              <small>{{ item.student_count }} 人</small></label
            >
          </fieldset>
          <label v-if="subjectiveTypes.includes(form.type)" class="span-2">题目说明
            <textarea v-model="form.statement" rows="6" required maxlength="20000" placeholder="说明作答任务、分析或证明要求；学生在线提交纯文本答案。" />
          </label>
          <fieldset class="span-2">
            <legend>关联知识点（可多选，用于学习分析）</legend>
            <p class="muted">仅关联确实考查的知识点。发布后冻结；未关联的旧作业不会被自动猜测分类。</p>
            <label v-for="topic in topics" :key="topic.id" class="check-row"><input v-model="form.topic_ids" type="checkbox" :value="topic.id">{{ topic.code }} · {{ topic.name }}</label>
            <p v-if="!topics.length" class="muted">暂无知识点，可先在知识点目录创建。</p>
          </fieldset>
          <fieldset v-if="form.type === 'FINAL_PROJECT'" class="span-2" aria-describedby="grading-weight-help">
            <legend>成绩组成</legend>
            <div class="form-grid">
              <label>教师评分比例（%）<input v-model.number="teacherWeightPercent" aria-label="教师评分比例（%）" type="number" min="0" max="100" step="0.01" required :aria-invalid="Boolean(weightError)" aria-describedby="grading-weight-help grading-weight-error" /></label>
              <label>同伴评审比例（%）<input v-model.number="reviewWeightPercent" aria-label="同伴评审比例（%）" type="number" min="0" max="100" step="0.01" required :aria-invalid="Boolean(weightError)" aria-describedby="grading-weight-help grading-weight-error" /></label>
            </div>
            <p id="grading-weight-help" class="muted">默认教师 60%、同伴 40%，合计须为 100%。发布前可修改，发布后固定。高风险作业由教师复核给出最终分。</p>
            <p v-if="weightError" id="grading-weight-error" class="notice notice-error" role="alert">{{ weightError }}</p>
          </fieldset>
        </div>
        <ProgrammingProblemEditor
          v-if="form.type === 'PROGRAMMING'"
          :problem="form.programming_problem"
        />
        <div v-else-if="form.type === 'FINAL_PROJECT'" class="rubric-editor">
          <div class="section-heading">
            <div>
              <h3>评分量表</h3>
              <p>各评分项合计建议为 100 分。</p>
            </div>
            <button
              class="button button-secondary button-small"
              type="button"
              @click="addRubric"
            >
              添加评分项
            </button>
          </div>
          <div
            v-for="(item, index) in form.rubric_items"
            :key="index"
            class="rubric-row"
          >
            <span>{{ index + 1 }}</span
            ><label>名称<input v-model="item.name" required /></label
            ><label
              >满分<input
                v-model.number="item.max_score"
                type="number"
                min="1"
                step="0.5"
                required /></label
            ><label>评分说明<input v-model="item.description" /></label
            ><button
              class="icon-button"
              type="button"
              :disabled="form.rubric_items.length === 1"
              aria-label="删除评分项"
              @click="removeRubric(index)"
            >
              ×
            </button>
          </div>
        </div>
      </fieldset>
      <div class="form-actions">
        <button
          class="button button-secondary"
          type="button"
          :disabled="busy"
          @click="showForm = false"
        >
          取消</button
        ><button class="button" :disabled="busy">
          {{ busy ? '正在保存…' : '保存草稿' }}
        </button>
      </div>
    </form>
    <section class="data-section">
      <div class="list-tools">
        <div class="list-tabs" role="group" aria-label="筛选作业">
          <button v-for="item in filters" :key="item.value" type="button" :aria-pressed="filter === item.value" @click="filter = item.value">{{ item.label }}</button>
        </div>
        <label class="search-field"><UiIcon name="search" /><input v-model="query" type="search" aria-label="搜索作业" placeholder="搜索作业名称" /></label>
      </div>
      <div v-if="filteredAssignments.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>作业</th>
              <th>状态</th>
              <th>提交</th>
              <th>评审任务</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredAssignments" :key="item.id">
              <td>
                <div class="assignment-title-cell"><span class="assignment-cover"><AssignmentArtwork :assignment="item" /></span><div><strong>{{ item.title }}</strong
                ><small>{{
                  assignmentTypeLabel(item.type)
                }}</small></div></div>
              </td>
              <td>
                <span class="status-chip" :data-state="item.status">{{
                  item.closed_at ? '已关闭' : stateName[item.status] || '状态待更新'
                }}</span>
              </td>
              <td>{{ item.submission_count }}</td>
              <td>{{ item.type === 'FINAL_PROJECT' ? item.review_task_count : '不适用' }}</td>
              <td>
                <div class="toolbar">
                  <RouterLink :to="`/teacher/assignments/${item.id}`"
                    >管理</RouterLink
                  ><button
                    v-if="item.status === 'DRAFT' && !item.closed_at"
                    class="button button-secondary button-small"
                    :disabled="busy"
                    @click="edit(item)"
                  >
                    编辑</button
                  ><button
                    class="button button-secondary button-small"
                    :disabled="busy"
                    @click="toggleClosed(item)"
                  >{{ item.closed_at ? '恢复' : '关闭' }}</button><button
                    class="button button-secondary button-small"
                    :disabled="busy"
                    @click="remove(item)"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state">
        <h3>{{ assignments.length ? '没有找到符合条件的作业' : '还没有作业' }}</h3>
        <p>{{ assignments.length ? '试试其他名称，或切换到全部作业。' : '点击“新建作业”开始。' }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.assignment-title-cell { display: flex; align-items: center; gap: 16px; min-width: 180px; }
.assignment-title-cell > div { min-width: 0; }
.assignment-cover { flex: none; width: 80px; height: 58px; background: var(--art-gradient); border-radius: 14px; overflow: hidden; }
.assignment-cover :deep(svg) { width: 100%; height: 100%; display: block; }
@media(max-width:760px) { .assignment-cover { width: 58px; height: 50px; } }
</style>
