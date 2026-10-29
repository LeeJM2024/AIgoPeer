<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  createTeacherGrade,
  correctTeacherGrade,
  getGradingWorkspace,
  lockTeacherGrade,
  publishResults,
  getPublicationReadiness,
  getGradeHistory,
  createTeacherFinalReview,
} from '../../api/teacher'
import { errorMessages } from '../../api/errors'
import { currentUser } from '../../api/auth'
import SubmissionEvidence from '../../components/teacher/SubmissionEvidence.vue'

const id = Number(useRoute().params.id),
  data = ref(null),
  selectedId = ref(null),
  correctionMode = ref(false)
const form = reactive({
    scores: {},
    comment: '',
    reason: '',
    finalScore: '',
    finalReason: '',
  }),
  error = ref(''),
  notice = ref(''),
  busy = ref(false),
  history = ref([]),
  readiness = ref(null)
let selectionVersion = 0
const gradingEditor = ref(null), finalReviewForm = ref(null)
const selected = computed(() =>
  data.value?.submissions.find((s) => s.id === selectedId.value),
)
const published = computed(
  () => data.value?.assignment.status === 'PUBLISHED_RESULT',
)
const scorePreviewNote = computed(() => {
  const state = selected.value?.score_preview_state
  const messages = {
    PUBLISHED: '已发布，成绩已冻结',
    MATERIAL_NOT_VALID: '等待材料检查通过',
    FINAL_REVIEW_REQUIRED: '待教师最终复核',
    TEACHER_GRADE_REQUIRED: '等待教师评分',
    REVIEWS_INCOMPLETE: '等待五位评委全部提交',
    AGGREGATE_NOT_READY: '等待生成评审综合分',
    AGGREGATE_STALE: '评审已修改，需重新聚合',
    FINAL_REVIEW_LOCKED: '采用教师复核最终分 · 未发布',
  }
  if (messages[state]) return messages[state]
  if (state === 'WEIGHTED' || state === 'TEACHER_GRADE_UNLOCKED') {
    const assignment = data.value.assignment
    const teacher = Math.round(Number(assignment.teacher_weight) * 10000) / 100
    const review = Math.round(Number(assignment.designated_review_weight) * 10000) / 100
    const status = state === 'TEACHER_GRADE_UNLOCKED' ? '教师分待锁定' : '未发布'
    return `教师 ${teacher}% + 评审 ${review}% · ${status}`
  }
  return '等待评分数据'
})
const isInitialTeacher = computed(
  () =>
    history.value.find((g) => g.version === 1)?.entered_by ===
    currentUser()?.id,
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
  form.finalScore = item.final_review_score ?? ''
  form.finalReason = ''
  try {
    const rows = await getGradeHistory(item.id)
    if (selectionVersion === version) history.value = rows
  } catch (err) {
    if (selectionVersion === version) error.value = err.message
  }
}
function blockerMessage(blocker) {
  const author = blocker.author_name
    ? `${blocker.author_name}（${blocker.student_no}）：`
    : ''
  return author + (errorMessages[blocker.code] || '请核对作业状态，刷新后重试。')
}
function blockerSubmission(blocker) {
  return data.value?.submissions.find((item) => item.id === blocker.submission_id)
}
async function openBlocker(blocker) {
  const item = blockerSubmission(blocker)
  if (!item || busy.value) return
  await select(item)
  await nextTick()
  if (selectedId.value !== item.id) return
  const target = blocker.code === 'TEACHER_FINAL_REVIEW_REQUIRED' && finalReviewForm.value
    ? finalReviewForm.value
    : gradingEditor.value
  target?.scrollIntoView?.({ behavior: 'auto', block: 'start' })
  const focusTarget = target === finalReviewForm.value
    ? target.querySelector('input')
    : target
  focusTarget?.focus({ preventScroll: true })
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
async function saveFinalReview() {
  if (form.finalScore === '') {
    error.value = '请填写复核最终分。'
    return
  }
  if (
    !confirm('复核最终分将直接作为本作品最终成绩，锁定后不可修改。确认提交？')
  )
    return
  await perform(
    () =>
      createTeacherFinalReview(selected.value.id, {
        final_score: Number(form.finalScore),
        reason: form.finalReason,
      }),
    '复核最终分已锁定；高风险异常已自动归档。',
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
        <p>{{ data?.assignment.title }}</p>
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
    <div v-if="!data && !error" class="skeleton-page workspace-loading" role="status" aria-busy="true">
      正在加载学生提交与评分数据…
    </div>
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
            <button
              v-if="blockerSubmission(blocker)"
              type="button"
              class="blocker-action"
              :disabled="busy"
              @click="openBlocker(blocker)"
            >{{ blockerMessage(blocker) }}<span aria-hidden="true"> →</span></button>
            <RouterLink
              v-else-if="blocker.code === 'OPEN_ANOMALIES_REQUIRE_REVIEW'"
              :to="`/teacher/assignments/${id}/reviews`"
            >{{ blockerMessage(blocker) }}<span aria-hidden="true"> →</span></RouterLink>
            <template v-else>{{ blockerMessage(blocker) }}</template>
          </li>
        </ul>
        <p class="muted">
          完成上方事项后即可发布成绩。
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
        <section v-if="selected" ref="gradingEditor" class="grading-editor" tabindex="-1" aria-labelledby="selected-work-heading">
          <div class="student-summary">
            <div>
              <h2 id="selected-work-heading">{{ selected.author_name }}</h2>
              <p>{{ selected.student_no }} · {{ selected.anonymous_token }}</p>
            </div>
            <div class="score-comparison">
              <span
                >评审综合分<strong>{{
                  selected.aggregate_score ?? '待生成'
                }}</strong></span
              ><span
                >教师评分<strong>{{
                  selected.teacher_score ?? '—'
                }}</strong></span
              >
              <span class="score-preview" aria-live="polite">
                {{ published ? '最终总分' : '预计总分' }}
                <strong>{{ selected.score_preview == null ? '—' : Number(selected.score_preview).toFixed(2) }}</strong>
                <small>{{ scorePreviewNote }}</small>
              </span>
            </div>
          </div>
          <p
            v-if="
              selected.final_review_status ===
              'ESCALATED_FOR_TEACHER_FINAL_REVIEW'
            "
            class="notice notice-error"
          >
            这份作业需要最终复核。请核对材料和评审记录后填写复核最终分。
          </p>
          <p
            v-else-if="selected.final_review_status === 'FINAL_REVIEW_LOCKED'"
            class="notice notice-success"
          >
            复核最终分已锁定：{{ selected.final_review_score }}。
          </p>
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
          </div>
          <div class="grading-content"><SubmissionEvidence
            :key="selected.id + ':' + selected.final_review_status"
            :submission-id="selected.id"
            :rubric-items="data.rubric_items"
          />
          <div class="scoring-column"><p v-if="!eligible && !published" class="notice notice-error">
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
                >教师反馈（选填）<textarea
                  v-model="form.comment"
                  rows="4"
                  maxlength="5000"
                /></label
              ><label v-if="correctionMode" class="spaced-label"
                >更正原因（选填）<input
                  v-model="form.reason"
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
          <form
            v-if="
              selected.final_review_status ===
                'ESCALATED_FOR_TEACHER_FINAL_REVIEW' &&
              data.assignment.status === 'TEACHER_GRADING' &&
              !published
            "
            ref="finalReviewForm"
            class="data-section final-review-form"
            aria-labelledby="final-review-heading"
            @submit.prevent="saveFinalReview"
          >
            <h3 id="final-review-heading">高风险作品复核最终分</h3>
            <p>确认后，这个分数将作为最终成绩。</p>
            <p
              v-if="!selected.locked_at || !isInitialTeacher"
              class="notice notice-error"
            >
              先锁定教师初评，再由最初评分的同一位教师录入复核最终分。
            </p>
            <label
              >复核最终分<input
                v-model="form.finalScore"
                type="number"
                min="0"
                :max="
                  data.rubric_items.reduce((n, r) => n + Number(r.max_score), 0)
                "
                step="0.01"
                required
            /></label>
            <label
              >复核理由（选填）<textarea
                v-model="form.finalReason"
                rows="3"
                maxlength="2000"
              />
            </label>
            <button
              class="button"
              :disabled="busy || !selected.locked_at || !isInitialTeacher"
            >
              锁定复核最终分
            </button>
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
          </section></div></div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.blocker-action { display: inline; padding: 4px 0; border: 0; border-radius: 4px; background: transparent; color: var(--primary); text-align: left; line-height: inherit; text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
.blocker-action:hover { text-decoration-thickness: 2px; }
.grading-editor, .final-review-form { scroll-margin-top: 24px; }
.workspace-loading { display: grid; place-items: center; padding: 24px; color: var(--muted); }
.score-comparison .score-preview { border: 1px solid var(--border); max-width: 100%; }
.score-preview small { font-size: 12px; line-height: 1.5; }
.grading-content { display: grid; grid-template-columns: minmax(0,1fr); gap: 26px; align-items: start; }
.scoring-column { min-width: 0; padding: 22px; border-radius: 24px; background: var(--surface); }
.grading-content :deep(.evidence-section) { margin-top: 0; border-top: 0; padding-top: 0; }
@media(min-width:1350px) { .grading-content { grid-template-columns: minmax(0,1.05fr) minmax(0,1fr); } .score-sheet > label { align-items: flex-start; flex-wrap: wrap; gap: 10px; } }
@media(max-width:760px) { .scoring-column { padding: 18px 14px; } }
</style>
