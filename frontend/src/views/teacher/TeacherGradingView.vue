<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  createTeacherGrade,
  correctTeacherGrade,
  getGradingWorkspace,
  lockTeacherGrade,
  publishResults,
  getPublicationReadiness,
  getGradeHistory,
} from '../../api/teacher'
import { errorMessages } from '../../api/errors'

const id = Number(useRoute().params.id),
  data = ref(null),
  selectedId = ref(null),
  correctionMode = ref(false)
const form = reactive({ scores: {}, comment: '', reason: '' }),
  error = ref(''),
  notice = ref(''),
  busy = ref(false),
  history = ref([]),
  readiness = ref(null)
let selectionVersion = 0
const selected = computed(() =>
  data.value?.submissions.find((s) => s.id === selectedId.value),
)
const published = computed(
  () => data.value?.assignment.status === 'PUBLISHED_RESULT',
)
const eligible = computed(
  () =>
    selected.value?.status === 'VALID' &&
    selected.value?.material_status === 'VALID' &&
    ['REVIEWER_GRADING', 'AGGREGATING', 'TEACHER_GRADING'].includes(
      data.value?.assignment.status,
    ),
)
const editable = computed(
  () =>
    eligible.value &&
    !published.value &&
    (!selected.value?.teacher_grade_id || correctionMode.value),
)
const total = computed(() =>
  Object.values(form.scores)
    .reduce((n, v) => n + (Number(v) || 0), 0)
    .toFixed(2),
)
async function select(item) {
  const version = ++selectionVersion
  selectedId.value = item.id
  correctionMode.value = false
  form.scores = {}
  history.value = []
  data.value.rubric_items.forEach(
    (r) => (form.scores[r.id] = item.rubric_scores_json?.[r.id] ?? ''),
  )
  form.comment = item.feedback || ''
  form.reason = ''
  try {
    const rows = await getGradeHistory(item.id)
    if (selectionVersion === version) history.value = rows
  } catch (err) {
    if (selectionVersion === version) error.value = err.message
  }
}
async function load() {
  const [workspace, checks] = await Promise.all([
    getGradingWorkspace(id),
    getPublicationReadiness(id),
  ])
  data.value = workspace
  readiness.value = checks
  const item =
    workspace.submissions.find((s) => s.id === selectedId.value) ||
    workspace.submissions[0]
  if (item) await select(item)
}
onMounted(async () => {
  try {
    await load()
  } catch (err) {
    error.value = err.message
  }
})
async function perform(action, success) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
    notice.value = success
    await load()
  } catch (err) {
    error.value = err.message
    if (err.status === 424 || err.status === 409) {
      try {
        readiness.value = await getPublicationReadiness(id)
      } catch {
        /* Keep the original actionable error. */
      }
    }
  } finally {
    busy.value = false
  }
}
async function save() {
  if (
    !editable.value ||
    data.value.rubric_items.some(
      (r) => form.scores[r.id] === '' || form.scores[r.id] == null,
    )
  ) {
    error.value = '请填写全部评分项。'
    return
  }
  const submissionId = selected.value.id
  const payload = {
    rubric_scores: data.value.rubric_items.map((r) => ({
      rubric_item_id: r.id,
      score: Number(form.scores[r.id]),
    })),
    comment: form.comment,
  }
  const correction = correctionMode.value
  await perform(
    () =>
      correction
        ? correctTeacherGrade(submissionId, {
            ...payload,
            reason: form.reason,
            expected_version: selected.value.teacher_grade_version,
          })
        : createTeacherGrade(submissionId, payload),
    correction
      ? '更正版本已保存，请核对后锁定。'
      : '评分已保存，请核对后锁定。',
  )
}
function lock() {
  const gradeId = selected.value.teacher_grade_id
  if (confirm('锁定后只能通过新增更正版本修改。确认锁定当前评分？'))
    perform(() => lockTeacherGrade(gradeId), '当前版本已锁定。')
}
function publishAll() {
  if (
    confirm(
      `确认发布 ${readiness.value.submission_count} 份成绩？发布后本工作台将只读。`,
    )
  )
    perform(() => publishResults(id), '全部成绩已发布。')
}
</script>

<template>
  <div class="view-stack grading-page">
    <nav class="breadcrumbs">
      <RouterLink :to="`/teacher/assignments/${id}`">{{
        data?.assignment.title || '作业详情'
      }}</RouterLink
      ><span>/</span><span>评分工作台</span>
    </nav>
    <header class="page-heading">
      <div>
        <h1>评分工作台</h1>
        <p>教师独立录分，锁定最新版本后，按固定权重发布成绩。</p>
      </div>
      <div class="toolbar">
        <RouterLink
          class="button button-secondary"
          :to="`/teacher/assignments/${id}/reviews`"
          >评审与异常</RouterLink
        ><button
          class="button"
          :disabled="busy || published || !readiness?.ready"
          @click="publishAll"
        >
          {{ published ? '成绩已发布' : '发布全部成绩' }}
        </button>
      </div>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <div v-if="!data && !error" class="skeleton-page" />
    <template v-if="data">
      <section v-if="published" class="notice notice-success">
        成绩已发布，评分和更正入口已关闭。<RouterLink
          :to="`/teacher/assignments/${id}/statistics`"
          >查看并导出已发布成绩</RouterLink
        >
      </section>
      <details v-else-if="readiness && !readiness.ready" class="data-section">
        <summary>发布前还有 {{ readiness.blockers.length }} 项需要处理</summary>
        <ul class="blocker-list">
          <li v-for="(blocker, index) in readiness.blockers" :key="index">
            {{
              blocker.author_name
                ? `${blocker.author_name}（${blocker.student_no}）：`
                : ''
            }}{{ errorMessages[blocker.code] || blocker.code }}
          </li>
        </ul>
        <p class="muted">
          请先完成跨班评审并等待聚合结果，处理异常后再发布成绩。
        </p>
      </details>
      <div class="grading-layout">
        <aside class="submission-index" aria-label="学生提交列表">
          <button
            v-for="item in data.submissions"
            :key="item.id"
            :disabled="busy"
            :class="{ selected: item.id === selectedId }"
            @click="select(item)"
          >
            <span
              ><strong>{{ item.author_name }}</strong
              ><small
                >{{ item.student_no }} · {{ item.class_name }}</small
              ></span
            ><span class="grade-state">{{
              item.published_at
                ? '已发布'
                : item.status !== 'VALID' || item.material_status !== 'VALID'
                  ? '材料未通过'
                  : item.locked_at
                    ? '已锁定'
                    : item.teacher_grade_id
                      ? '待锁定'
                      : '未评分'
            }}</span>
          </button>
          <p v-if="!data.submissions.length" class="empty-state compact">
            暂无学生提交
          </p>
        </aside>
        <section v-if="selected" class="grading-editor">
          <div class="student-summary">
            <div>
              <h2>{{ selected.author_name }}</h2>
              <p>{{ selected.student_no }} · {{ selected.anonymous_token }}</p>
            </div>
            <div class="score-comparison">
              <span
                >同伴聚合<strong>{{
                  selected.aggregate_score ?? '待生成'
                }}</strong></span
              ><span
                >教师当前分<strong>{{
                  selected.teacher_score ?? '—'
                }}</strong></span
              >
            </div>
          </div>
          <div class="evidence-placeholder">
            <strong
              >材料状态：{{
                selected.material_status === 'VALID'
                  ? '检查通过'
                  : selected.material_status === 'INVALID'
                    ? '检查未通过'
                    : '待检查'
              }}</strong
            >
            <p v-if="selected.missing_items?.length">
              缺少：{{ selected.missing_items.join('、') }}
            </p>
            <p>当前暂无在线材料，请通过课程收集渠道核对原始证据后评分。</p>
          </div>
          <p v-if="!eligible && !published" class="notice notice-error">
            当前提交或作业阶段不允许评分。
          </p>
          <form @submit.prevent="save">
            <fieldset class="bare-fieldset" :disabled="busy || !editable">
              <div class="score-sheet">
                <label v-for="rubric in data.rubric_items" :key="rubric.id"
                  ><span
                    ><strong>{{ rubric.name }}</strong
                    ><small>{{ rubric.description }}</small></span
                  ><span class="score-input"
                    ><input
                      v-model="form.scores[rubric.id]"
                      type="number"
                      min="0"
                      :max="rubric.max_score"
                      step="0.01"
                      required
                    /><b>/ {{ rubric.max_score }}</b></span
                  ></label
                >
              </div>
              <label
                >教师反馈<textarea
                  v-model="form.comment"
                  rows="4"
                  maxlength="5000"
                /></label
              ><label v-if="correctionMode" class="spaced-label"
                >更正原因<input
                  v-model="form.reason"
                  required
                  minlength="3"
                  maxlength="1000"
              /></label>
            </fieldset>
            <div class="form-actions">
              <div class="total-score">
                本次合计 <strong>{{ total }}</strong>
              </div>
              <button v-if="editable" class="button" :disabled="busy">
                {{ correctionMode ? '保存更正版本' : '保存教师评分' }}</button
              ><button
                v-if="
                  eligible &&
                  !published &&
                  selected.teacher_grade_id &&
                  !selected.locked_at
                "
                class="button button-secondary"
                type="button"
                :disabled="busy"
                @click="lock"
              >
                锁定当前评分</button
              ><button
                v-if="
                  eligible &&
                  !published &&
                  selected.locked_at &&
                  !correctionMode
                "
                class="button button-secondary"
                type="button"
                :disabled="busy"
                @click="correctionMode = true"
              >
                创建更正版本</button
              ><button
                v-if="correctionMode"
                class="button button-secondary"
                type="button"
                :disabled="busy"
                @click="select(selected)"
              >
                取消更正
              </button>
            </div>
          </form>
          <section class="grade-history">
            <h3>评分历史</h3>
            <p v-if="!history.length" class="muted">尚未保存评分。</p>
            <details v-for="grade in history" :key="grade.id">
              <summary>
                v{{ grade.version }} · {{ grade.total_score }} 分 ·
                {{ grade.locked_at ? '已锁定' : '待锁定' }} ·
                {{ grade.entered_by_name }}
              </summary>
              <p>
                {{
                  grade.correction_reason
                    ? `更正原因：${grade.correction_reason}`
                    : '首次评分'
                }}
              </p>
              <p>反馈：{{ grade.feedback || '未填写' }}</p>
              <dl>
                <div v-for="rubric in data.rubric_items" :key="rubric.id">
                  <dt>{{ rubric.name }}</dt>
                  <dd>
                    {{ grade.rubric_scores_json[rubric.id] ?? '—' }} /
                    {{ rubric.max_score }}
                  </dd>
                </div>
              </dl>
              <small class="muted"
                >保存于 {{ new Date(grade.created_at).toLocaleString() }}</small
              >
            </details>
          </section>
        </section>
      </div>
    </template>
  </div>
</template>
