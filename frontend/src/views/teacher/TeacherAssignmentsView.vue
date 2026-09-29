<script setup>
import { onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  createAssignment,
  getAssignments,
  getClasses,
  getAssignment,
  editAssignment,
  deleteAssignment,
} from '../../api/teacher'

const editingId = ref(null)
const notice = ref('')
const assignments = ref([])
const classes = ref([])
const showForm = ref(false)
const error = ref('')
const busy = ref(false)
const stateName = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
  SUBMITTING: '提交中',
  REVIEWER_INITIALIZING: '任务初始化',
  REVIEWER_GRADING: '跨班评审中',
  AGGREGATING: '评分聚合中',
  TEACHER_GRADING: '教师评分中',
  PUBLISHED_RESULT: '成绩已发布',
}
const form = reactive({
  title: '',
  type: 'FINAL_PROJECT',
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

async function load() {
  try {
    ;[assignments.value, classes.value] = await Promise.all([
      getAssignments(),
      getClasses(),
    ])
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
function removeRubric(index) {
  form.rubric_items.splice(index, 1)
  form.rubric_items.forEach((item, i) => (item.sort_order = i + 1))
}
function localTime(value) {
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}
function newDraft() {
  if (busy.value) return
  editingId.value = null
  form.title = ''
  form.class_ids = []
  form.submit_deadline = ''
  form.review_deadline = ''
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
  if (!confirm(`删除草稿“${item.title}”？此操作会删除其量表和评审组配置。`))
    return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await deleteAssignment(item.id)
    if (editingId.value === item.id) showForm.value = false
    await load()
    notice.value = '草稿已删除。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function submit() {
  error.value = ''
  if (form.class_ids.length !== 2) {
    error.value = '必须选择两个班级。'
    return
  }
  busy.value = true
  try {
    const payload = {
      ...form,
      submit_deadline: new Date(form.submit_deadline).toISOString(),
      review_deadline: new Date(form.review_deadline).toISOString(),
    }
    const result = editingId.value
      ? await editAssignment(editingId.value, payload)
      : await createAssignment(payload)
    notice.value = result.panels_reset
      ? '草稿已保存。班级发生变更，请重新配置评审组。'
      : '草稿已保存。'
    showForm.value = false
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="view-stack">
    <header class="page-heading">
      <div>
        <p class="section-label">课程规则</p>
        <h1>作业与评分</h1>
        <p>作业、Rubric、权重和跨班评审组是后续流程的唯一规则来源。</p>
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
            保存后仍为草稿，配置两组评审人后才能发布。修改适用班级将清空已有评审组。
          </p>
        </div>
      </div>
      <fieldset class="bare-fieldset" :disabled="busy">
        <div class="form-grid">
          <label
            >作业类型<select v-model="form.type">
              <option value="FINAL_PROJECT">期末微课作业</option>
              <option value="PROGRAMMING">
                编程作业（判题由学生模块接入）
              </option>
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
          <label
            >评审截止时间<input
              v-model="form.review_deadline"
              type="datetime-local"
              required
          /></label>
          <fieldset class="span-2">
            <legend>适用班级（必须选择两个）</legend>
            <label v-for="item in classes" :key="item.id" class="check-row"
              ><input
                v-model="form.class_ids"
                type="checkbox"
                :value="item.id"
                :disabled="
                  form.class_ids.length >= 2 &&
                  !form.class_ids.includes(item.id)
                "
              />{{ item.name }}
              <small>{{ item.student_count }} 人</small></label
            >
          </fieldset>
          <label
            >教师评分权重<input
              v-model.number="form.teacher_weight"
              type="number"
              min="0"
              max="1"
              step="0.05"
              required
          /></label>
          <label
            >跨班评审权重<input
              v-model.number="form.designated_review_weight"
              type="number"
              min="0"
              max="1"
              step="0.05"
              required
          /></label>
        </div>
        <div class="rubric-editor">
          <div class="section-heading">
            <div>
              <h3>评分量表</h3>
              <p>总分建议为 100；所有端均从这里动态读取。</p>
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
      <div v-if="assignments.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>作业</th>
              <th>状态</th>
              <th>提交</th>
              <th>评审任务</th>
              <th>教师/评审权重</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in assignments" :key="item.id">
              <td>
                <strong>{{ item.title }}</strong
                ><small>{{
                  item.type === 'FINAL_PROJECT' ? '期末项目' : '编程题'
                }}</small>
              </td>
              <td>
                <span class="status-chip">{{
                  stateName[item.status] || item.status
                }}</span>
              </td>
              <td>{{ item.submission_count }}</td>
              <td>{{ item.review_task_count }}</td>
              <td>
                {{ Number(item.teacher_weight) * 100 }}% /
                {{ Number(item.designated_review_weight) * 100 }}%
              </td>
              <td>
                <div class="toolbar">
                  <RouterLink :to="`/teacher/assignments/${item.id}`"
                    >管理</RouterLink
                  ><button
                    v-if="item.status === 'DRAFT'"
                    class="button button-secondary button-small"
                    :disabled="busy"
                    @click="edit(item)"
                  >
                    编辑</button
                  ><button
                    v-if="item.status === 'DRAFT'"
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
        <h3>还没有作业</h3>
        <p>创建后先配置两个方向的固定五人评审组。</p>
      </div>
    </section>
  </div>
</template>
