<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { downloadReviewMaterial, getMyReviewTasks, submitReview, reviseReview, openReviewAnswer } from '../api/reviewer'

const tasks = ref([])
const selectedTaskId = ref(null)
const error = ref('')
const notice = ref('')
const loading = ref(false)
const saving = ref(false)
const downloading = ref(false)
const scores = reactive({})
const comment = ref('')
const answer = ref(null)
const statusFilter = ref('PENDING')
const editing = ref(false)
const revisionReason = ref('')
const now = ref(Date.now())
const clockTimer = window.setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => window.clearInterval(clockTimer))

const selectedTask = computed(() => tasks.value.find((task) => task.task_id === selectedTaskId.value) ?? null)
const canAmend = computed(() => selectedTask.value?.can_amend && (!selectedTask.value.review_deadline ||
  new Date(selectedTask.value.review_deadline).getTime() > now.value))
const formWritable = computed(() => selectedTask.value?.status === 'IN_PROGRESS' || (editing.value && canAmend.value))

function resetForm(task) {
  answer.value = null
  Object.keys(scores).forEach((key) => delete scores[key])
  task?.rubric_items.forEach((item) => { scores[item.id] = '' })
  task?.review?.rubric_scores.forEach((item) => { scores[item.rubric_item_id] = item.score })
  comment.value = task?.review?.comment || ''
  editing.value = false
  revisionReason.value = ''
}

async function loadTasks(preserveForm = false) {
  loading.value = true
  error.value = ''
  try {
    tasks.value = await getMyReviewTasks(statusFilter.value)
    if (!selectedTask.value && tasks.value.length) {
      selectedTaskId.value = tasks.value[0].task_id
      resetForm(tasks.value[0])
    } else if (!preserveForm) resetForm(selectedTask.value)
  } catch (err) {
    error.value = err.message
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function changeStatus(value) {
  if (saving.value || downloading.value || loading.value) return
  statusFilter.value = value
  selectedTaskId.value = null
  notice.value = ''
  await loadTasks()
}

function selectTask(task) {
  if (saving.value || downloading.value) return
  selectedTaskId.value = task.task_id
  resetForm(task)
  notice.value = ''
}

async function downloadMaterial() {
  if (!selectedTask.value || downloading.value || saving.value) return
  const task = selectedTask.value
  downloading.value = true
  error.value = ''
  notice.value = ''
  try {
    if (task.answer_url) {
      answer.value = await openReviewAnswer(task.task_id)
      notice.value = '匿名答案已打开，请按评分标准完成评阅。'
      await loadTasks(true)
      return
    }
    const blob = await downloadReviewMaterial(task.task_id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `anonymous-review-${task.anonymous_token}.zip`
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    notice.value = '匿名材料已下载。请依据材料完成全部 Rubric 评分。'
    await loadTasks(true)
  } catch (err) {
    error.value = err.message
  } finally {
    downloading.value = false
  }
}

async function saveReview() {
  if (!selectedTask.value || saving.value || downloading.value) return
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = selectedTask.value
    const amending = task.status === 'SUBMITTED'
    if (amending && (!editing.value || !canAmend.value || revisionReason.value.trim().length < 3)) return
    const payload = {
      rubric_scores: selectedTask.value.rubric_items.map((item) => ({
        rubric_item_id: item.id,
        score: Number(scores[item.id])
      })),
      comment: comment.value
    }
    if (amending) await reviseReview(task.task_id, {
      ...payload, reason: revisionReason.value.trim(), expected_version: task.review.version
    })
    else await submitReview(task.task_id, payload)
    statusFilter.value = 'SUBMITTED'
    await loadTasks()
    notice.value = amending
      ? '评分修改已保存，修改原因和前后记录已同步到教师端。'
      : '评分已提交。评审开放期间可在“已提交”中修改，每次需填写原因。'
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

onMounted(loadTasks)
</script>

<template>
  <section class="reviewer-page">
    <header class="reviewer-page__header">
      <p class="eyebrow">定向匿名评审</p>
      <h1>我的评审任务</h1>
      <p>只显示系统分配给你的跨班匿名材料。评审开放期间可修改已提交评分，每次修改需填写原因，教师可查看完整记录。</p>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <nav class="review-tabs" aria-label="评审任务状态">
      <button type="button" :aria-pressed="statusFilter === 'PENDING'" :disabled="saving || downloading || loading" @click="changeStatus('PENDING')">待完成</button>
      <button type="button" :aria-pressed="statusFilter === 'SUBMITTED'" :disabled="saving || downloading || loading" @click="changeStatus('SUBMITTED')">已提交</button>
      <button type="button" :disabled="saving || downloading || loading" @click="loadTasks()">刷新任务</button>
    </nav>
    <p v-if="loading" class="muted" role="status">正在加载任务…</p>
    <p v-else-if="tasks.length === 0" class="empty-state">{{ statusFilter === 'SUBMITTED' ? '当前没有已提交的匿名评审任务。' : '当前没有待完成的匿名评审任务。' }}</p>

    <div v-else class="reviewer-layout">
      <aside class="task-list" aria-label="评审任务列表">
        <button
          v-for="task in tasks"
          :key="task.task_id"
          type="button"
          :disabled="saving || downloading"
          :class="{ selected: selectedTaskId === task.task_id }"
          :aria-pressed="selectedTaskId === task.task_id"
          @click="selectTask(task)"
        >
          <strong>匿名作业 {{ task.anonymous_token }}</strong>
          <small>{{ task.assignment_title }}</small>
          <span>{{ task.status === 'SUBMITTED' ? `已提交 · v${task.review?.version || 1}` : task.status === 'IN_PROGRESS' ? '评审中' : '待评审' }}</span>
        </button>
      </aside>

      <form v-if="selectedTask" class="review-form" @submit.prevent="saveReview">
        <div class="review-form__heading">
          <div>
            <p class="eyebrow">匿名编号 {{ selectedTask.anonymous_token }}</p>
            <h2>{{ selectedTask.assignment_title }}</h2>
            <p>截止时间：{{ selectedTask.review_deadline ? new Date(selectedTask.review_deadline).toLocaleString('zh-CN') : '未设置' }}</p>
          </div>
          <span class="status-badge">{{ selectedTask.status === 'SUBMITTED' ? (editing ? '正在修改' : '已提交') : selectedTask.status === 'IN_PROGRESS' ? '评审中' : '待开始' }}</span>
        </div>

        <section class="anonymous-material">
          <h3>匿名材料</h3>
          <p>{{ selectedTask.answer_url ? '在线答案不展示作者身份。请不要尝试识别或推测作者。' : '材料包已移除原始文件名和可处理元数据。请不要尝试识别或推测作者身份。' }}</p>
          <button
            class="button button-secondary"
            type="button"
            :disabled="(!selectedTask.materials.length && !selectedTask.answer_url) || downloading || saving"
            @click="downloadMaterial"
          >
            {{ selectedTask.status === 'SUBMITTED' ? (selectedTask.answer_url ? '查看匿名答案' : '下载匿名材料') : selectedTask.answer_url ? '打开匿名答案并开始评审' : '下载匿名材料并开始评审' }}
          </button>
          <small v-if="!selectedTask.materials.length && !selectedTask.answer_url">材料仍在匿名化核验中，暂不可评审。</small>
          <section v-if="answer" aria-label="匿名在线答案"><h4>题目说明</h4><pre>{{ answer.statement }}</pre><h4>匿名答案</h4><pre>{{ answer.content }}</pre></section>
        </section>

        <fieldset :disabled="!formWritable || saving || downloading">
          <legend>Rubric 评分</legend>
          <label v-for="item in selectedTask.rubric_items" :key="item.id" class="score-row">
            <span><strong>{{ item.name }}</strong><small>{{ item.description || '按此维度评价材料质量。' }}</small></span>
            <span class="score-input"><input v-model="scores[item.id]" type="number" min="0" :max="item.max_score" step="0.01" required><b>/ {{ item.max_score }}</b></span>
          </label>
          <label class="comment-field">评语<textarea v-model="comment" rows="5" minlength="1" maxlength="10000" required placeholder="请说明评分依据和可改进之处。" /></label>
          <label v-if="editing" class="comment-field">修改原因（教师可见）<textarea v-model="revisionReason" rows="3" minlength="3" maxlength="1000" required placeholder="例如：核对代码后发现上一版分数误填，现予以更正。" /></label>
        </fieldset>
        <div class="form-actions">
          <template v-if="selectedTask.status === 'SUBMITTED'">
            <template v-if="!editing">
              <span class="muted">{{ canAmend ? `当前评分 v${selectedTask.review?.version || 1}，可填写原因后修改。` : '评审已截止或已进入后续评分阶段，当前评分只读。' }}</span>
              <button v-if="canAmend" class="button" type="button" :disabled="saving || downloading" @click="editing = true">修改评分</button>
            </template>
            <template v-else>
              <button class="button button-secondary" type="button" :disabled="saving" @click="resetForm(selectedTask)">取消修改</button>
              <button class="button" type="submit" :disabled="!canAmend || saving || downloading || revisionReason.trim().length < 3">{{ saving ? '正在保存…' : '保存修改及原因' }}</button>
            </template>
          </template>
          <template v-else>
            <span v-if="selectedTask.status !== 'IN_PROGRESS'" class="muted">请先打开答案或下载匿名材料，系统会记录评审开始时间。</span>
            <button class="button" type="submit" :disabled="!formWritable || saving || downloading">{{ saving ? '正在提交…' : '提交评分' }}</button>
          </template>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.reviewer-page { display: grid; grid-template-columns: minmax(0,1fr); gap: 24px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 480px; overflow: auto; font: 14px/1.8 Consolas, 'Microsoft YaHei', monospace; }
.reviewer-page > * { min-width: 0; }
.reviewer-page__header h1 { margin: 4px 0 7px; }
.reviewer-page__header p:last-child { margin: 0; color: var(--muted); font-size: 13px; }
.eyebrow { margin: 0; color: var(--primary); font-size: 12px; font-weight: 600; }
.notice { color: var(--success); background: var(--success-soft); border: 1px solid #c0dfcc; }
.review-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.review-tabs button { min-height: 44px; padding: 8px 18px; border: 1px solid var(--border); border-radius: 14px; background: var(--surface); color: var(--ink); }
.review-tabs button[aria-pressed=true] { background: var(--primary-soft); border-color: var(--primary); color: var(--primary); }
.reviewer-layout { display: grid; grid-template-columns: 236px minmax(0,1fr); min-height: 560px; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
.task-list { background: var(--surface-subtle); border-right: 1px solid var(--border); }
.task-list button { display: grid; width: 100%; gap: 7px; padding: 20px 18px; border: 0; border-bottom: 1px solid var(--border); background: transparent; color: var(--ink); text-align: left; overflow-wrap: anywhere; }
.task-list button:hover { background: var(--primary-soft); }
.task-list button.selected { background: var(--primary-soft); color: var(--primary-hover); }
.task-list strong { font-weight: 600; font-size: 13px; }
.task-list small, .review-form small { color: var(--muted); font-size: 12px; }
.task-list span { font-size: 11px; color: var(--primary); }
.review-form { min-width: 0; padding: 26px; }
.review-form__heading { display: flex; justify-content: space-between; gap: 18px; border-bottom: 1px solid var(--border); padding-bottom: 22px; }
.review-form__heading > div { min-width: 0; overflow-wrap: anywhere; }
.review-form__heading h2 { margin: 6px 0; }
.review-form__heading p:last-child { margin: 0; color: var(--muted); font-size: 12px; }
.anonymous-material { margin: 22px 0; padding: 20px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-subtle); }
.anonymous-material h3 { margin-bottom: 8px; }
.anonymous-material p { margin: 0 0 14px; color: var(--muted); line-height: 1.8; font-size: 13px; }
.anonymous-material small { display: block; margin-top: 10px; }
.score-row { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px 0; border-top: 1px solid var(--border); }
.score-row:first-of-type { border-top: 0; }
.score-row > span:first-child { display: grid; gap: 5px; }
.score-row small { font-weight: 400; }
.score-input { display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.score-input input { width: 86px; text-align: right; }
.score-input b { color: var(--muted); font-size: 12px; }
.comment-field { margin-top: 14px; }
.form-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 22px; }
.form-actions > span { font-size: 12px; }
.empty-state { background: var(--surface); border: 1px solid var(--border); }
@media (max-width: 800px) { .reviewer-layout { grid-template-columns: minmax(0,1fr); } .task-list { max-height: 220px; overflow-y: auto; border-right: 0; border-bottom: 1px solid var(--border); } .task-list button { padding: 14px 18px; } }
@media (max-width: 680px) { .score-row, .review-form__heading, .form-actions { align-items: flex-start; flex-direction: column; } .review-form { padding: 18px; } .anonymous-material { padding: 16px; } }
</style>
