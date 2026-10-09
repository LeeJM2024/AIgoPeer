<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { downloadReviewMaterial, getMyReviewTasks, submitReview } from '../api/reviewer'

const tasks = ref([])
const selectedTaskId = ref(null)
const error = ref('')
const notice = ref('')
const loading = ref(false)
const saving = ref(false)
const scores = reactive({})
const comment = ref('')

const selectedTask = computed(() => tasks.value.find((task) => task.task_id === selectedTaskId.value) ?? null)

function resetForm(task) {
  Object.keys(scores).forEach((key) => delete scores[key])
  task?.rubric_items.forEach((item) => { scores[item.id] = '' })
  comment.value = ''
}

async function loadTasks() {
  loading.value = true
  error.value = ''
  try {
    tasks.value = await getMyReviewTasks()
    if (!selectedTask.value && tasks.value.length) {
      selectedTaskId.value = tasks.value[0].task_id
      resetForm(tasks.value[0])
    }
  } catch (err) {
    error.value = err.message
    tasks.value = []
  } finally {
    loading.value = false
  }
}

function selectTask(task) {
  selectedTaskId.value = task.task_id
  resetForm(task)
  notice.value = ''
}

async function downloadMaterial() {
  if (!selectedTask.value) return
  error.value = ''
  notice.value = ''
  try {
    const blob = await downloadReviewMaterial(selectedTask.value.task_id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `anonymous-review-${selectedTask.value.anonymous_token}.zip`
    anchor.click()
    URL.revokeObjectURL(url)
    notice.value = '匿名材料已下载。请依据材料完成全部 Rubric 评分。'
    await loadTasks()
  } catch (err) {
    error.value = err.message
  }
}

async function saveReview() {
  if (!selectedTask.value) return
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    await submitReview(selectedTask.value.task_id, {
      rubric_scores: selectedTask.value.rubric_items.map((item) => ({
        rubric_item_id: item.id,
        score: Number(scores[item.id])
      })),
      comment: comment.value,
      started_at: selectedTask.value.started_at ?? new Date().toISOString()
    })
    notice.value = '评分已提交，之后不能修改。'
    selectedTaskId.value = null
    await loadTasks()
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
      <p>只显示系统分配给你的跨班匿名材料。提交后评分不可修改。</p>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="loading" class="muted">正在加载任务…</p>
    <p v-else-if="tasks.length === 0" class="empty-state">当前没有待完成的匿名评审任务。</p>

    <div v-else class="reviewer-layout">
      <aside class="task-list" aria-label="待评审任务">
        <button
          v-for="task in tasks"
          :key="task.task_id"
          type="button"
          :class="{ selected: selectedTaskId === task.task_id }"
          @click="selectTask(task)"
        >
          <strong>匿名作业 {{ task.anonymous_token }}</strong>
          <small>{{ task.assignment_title }}</small>
          <span>{{ task.status === 'IN_PROGRESS' ? '评审中' : '待评审' }}</span>
        </button>
      </aside>

      <form v-if="selectedTask" class="review-form" @submit.prevent="saveReview">
        <div class="review-form__heading">
          <div>
            <p class="eyebrow">匿名编号 {{ selectedTask.anonymous_token }}</p>
            <h2>{{ selectedTask.assignment_title }}</h2>
            <p>截止时间：{{ selectedTask.review_deadline ? new Date(selectedTask.review_deadline).toLocaleString('zh-CN') : '未设置' }}</p>
          </div>
          <span class="status-badge">{{ selectedTask.status === 'IN_PROGRESS' ? '评审中' : '待开始' }}</span>
        </div>

        <section class="anonymous-material">
          <h3>匿名材料</h3>
          <p>材料包已移除原始文件名和可处理元数据。请不要尝试识别或推测作者身份。</p>
          <button
            class="button button-secondary"
            type="button"
            :disabled="!selectedTask.materials.length"
            @click="downloadMaterial"
          >
            下载匿名材料并开始评审
          </button>
          <small v-if="!selectedTask.materials.length">材料仍在匿名化核验中，暂不可评审。</small>
        </section>

        <fieldset :disabled="selectedTask.status !== 'IN_PROGRESS' || saving">
          <legend>Rubric 评分</legend>
          <label v-for="item in selectedTask.rubric_items" :key="item.id" class="score-row">
            <span><strong>{{ item.name }}</strong><small>{{ item.description || '按此维度评价材料质量。' }}</small></span>
            <span class="score-input"><input v-model="scores[item.id]" type="number" min="0" :max="item.max_score" step="0.01" required><b>/ {{ item.max_score }}</b></span>
          </label>
          <label class="comment-field">评语<textarea v-model="comment" rows="5" minlength="1" maxlength="10000" required placeholder="请说明评分依据和可改进之处。" /></label>
        </fieldset>
        <div class="form-actions">
          <span v-if="selectedTask.status !== 'IN_PROGRESS'" class="muted">请先下载匿名材料，系统会记录评审开始时间。</span>
          <button class="button" type="submit" :disabled="selectedTask.status !== 'IN_PROGRESS' || saving">{{ saving ? '正在提交…' : '提交评分' }}</button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.reviewer-page { display:grid; gap:22px; }.reviewer-page__header { padding:28px; border-radius:14px; color:#eaf7f0; background:linear-gradient(125deg,#063a2b,#0d5a42); }.reviewer-page__header h1 { margin:5px 0 8px; }.reviewer-page__header p:last-child { margin:0; color:#c9e6d4; }.eyebrow { margin:0; color:#34785c; font-size:13px; font-weight:750; }.reviewer-page__header .eyebrow { color:#9bd0af; }.notice { margin:0; padding:12px 14px; border-radius:8px; color:#165f3d; background:#e8f7ed; }.reviewer-layout { display:grid; grid-template-columns:250px minmax(0,1fr); min-height:560px; overflow:hidden; border:1px solid #cfe2d6; border-radius:12px; background:#fff; }.task-list { background:#f2f8f4; border-right:1px solid #cfe2d6; }.task-list button { display:grid; width:100%; gap:6px; padding:16px; border:0; border-bottom:1px solid #dcebe1; background:transparent; text-align:left; cursor:pointer; }.task-list button.selected { background:#fff; box-shadow:inset 3px 0 #0d5a42; }.task-list small,.task-list span,.review-form small { color:#61756a; }.task-list span { font-size:12px; font-weight:700; }.review-form { padding:26px; }.review-form__heading { display:flex; justify-content:space-between; gap:18px; border-bottom:1px solid #e2ece5; padding-bottom:18px; }.review-form__heading h2 { margin:5px 0; }.review-form__heading p:last-child { margin:0; color:#61756a; }.status-badge { height:max-content; padding:5px 9px; border-radius:99px; color:#17603f; background:#e5f5eb; font-size:12px; font-weight:700; }.anonymous-material { margin:20px 0; padding:18px; border-radius:9px; background:#f4f9f6; }.anonymous-material h3 { margin-bottom:8px; }.anonymous-material p { margin:0 0 14px; color:#52695d; line-height:1.55; }.score-row { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:13px 0; border-top:1px solid #e4ece6; }.score-row:first-of-type { border-top:0; }.score-row>span:first-child { display:grid; gap:4px; }.score-row small { font-weight:400; }.score-input { display:flex; align-items:center; gap:7px; white-space:nowrap; }.score-input input { width:92px; text-align:right; }.comment-field { margin-top:12px; }.form-actions { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-top:20px; }.empty-state { padding:28px; border:1px dashed #a6bfaf; border-radius:10px; color:#52695d; background:#fbfdfb; }.muted { color:#61756a; } @media (max-width:720px) { .reviewer-layout { grid-template-columns:1fr; }.task-list { display:flex; overflow:auto; border-right:0; border-bottom:1px solid #cfe2d6; }.task-list button { min-width:220px; }.score-row,.review-form__heading,.form-actions { align-items:flex-start; flex-direction:column; }.review-form { padding:18px; } }
</style>
