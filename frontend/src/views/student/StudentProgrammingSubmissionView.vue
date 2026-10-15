<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import StudentCodeEditor from '../../components/student/StudentCodeEditor.vue'
import ProgrammingSubmissionResult from '../../components/student/ProgrammingSubmissionResult.vue'
import ProgrammingSubmissionHistory from '../../components/student/ProgrammingSubmissionHistory.vue'
import { currentUser } from '../../api/auth'
import { getCodeSubmission, getProgrammingProblem, submitCode } from '../../api/student/programmingSubmissions'

const props = defineProps({ assignmentId: { type: String, required: true } })
const starterCode = '#include <iostream>\n\nint main() {\n  long long a, b;\n  std::cin >> a >> b;\n  std::cout << a + b << "\\n";\n  return 0;\n}\n'
const maxSourceBytes = 65536
const problem = ref(null)
const sourceCode = ref(starterCode)
const submission = ref(null)
const isLoading = ref(true)
const isSubmitting = ref(false)
const isRefreshing = ref(false)
const pollingStopped = ref(false)
const draftMessage = ref('')
const error = ref('')
const history = ref(null)
let pollTimer = null
let draftTimer = null
let pollAttempts = 0
let skipNextDraftSave = false

// Assignment-only legacy keys have no reliable owner and must not be restored.
const studentId = currentUser()?.id
const draftStorageKey = computed(() => studentId ? `algopeer:programming-draft:${studentId}:${props.assignmentId}` : null)
const sourceByteSize = computed(() => new Blob([sourceCode.value]).size)
const activeStatus = computed(() => ['QUEUED', 'RUNNING'].includes(submission.value?.status))

function stopPolling() {
  if (pollTimer) window.clearTimeout(pollTimer)
  pollTimer = null
}

function restoreDraft() {
  if (!draftStorageKey.value) return
  try {
    const savedDraft = window.localStorage.getItem(draftStorageKey.value)
    if (savedDraft) {
      sourceCode.value = savedDraft
      draftMessage.value = '已恢复本浏览器保存的草稿。'
    }
  } catch {
    draftMessage.value = '浏览器限制了本地草稿保存。'
  }
}

function saveDraft() {
  if (!draftStorageKey.value) return
  try {
    window.localStorage.setItem(draftStorageKey.value, sourceCode.value)
    draftMessage.value = '草稿已保存在当前浏览器。'
  } catch {
    draftMessage.value = '草稿保存失败，请复制代码后继续。'
  }
}

function clearDraft() {
  if (!window.confirm('确定清除本浏览器保存的草稿，并恢复示例代码吗？')) return
  try {
    if (draftStorageKey.value) window.localStorage.removeItem(draftStorageKey.value)
  } catch {
    // Clearing a draft should not prevent the student from continuing to edit.
  }
  skipNextDraftSave = true
  sourceCode.value = starterCode
  draftMessage.value = '草稿已清除，已恢复示例代码。'
}

async function loadProblem() {
  isLoading.value = true
  error.value = ''
  try {
    problem.value = await getProgrammingProblem(props.assignmentId)
  } catch (err) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}

async function pollResult(submissionId) {
  isRefreshing.value = true
  try {
    submission.value = await getCodeSubmission(submissionId)
    if (activeStatus.value && pollAttempts < 60) {
      pollAttempts += 1
      pollTimer = window.setTimeout(() => pollResult(submissionId), 2000)
    } else if (activeStatus.value) {
      pollingStopped.value = true
    } else {
      pollingStopped.value = false
    }
  } catch (err) {
    error.value = err.message
  } finally {
    isRefreshing.value = false
  }
}

function restoreCurrentSubmission(item) {
  if (!submission.value || item.version > submission.value.version) {
    stopPolling()
    submission.value = item
    pollAttempts = 0
    pollingStopped.value = false
    void pollResult(item.id)
  }
}

async function handleSubmit() {
  if (!sourceCode.value.trim()) {
    error.value = '请先输入 C++17 源代码。'
    return
  }
  if (sourceByteSize.value > maxSourceBytes) {
    error.value = `源代码不能超过 ${maxSourceBytes} 字节。`
    return
  }
  isSubmitting.value = true
  error.value = ''
  stopPolling()
  pollingStopped.value = false
  try {
    const created = await submitCode(props.assignmentId, sourceCode.value)
    submission.value = { id: created.submission_id, version: created.version, status: created.status }
    pollAttempts = 0
    void pollResult(created.submission_id)
    void history.value?.refresh(true)
  } catch (err) {
    error.value = err.code === 'INVALID_STATE'
      ? '作业已截止或当前状态不允许提交，请返回作业列表核对。'
      : err.message
  } finally {
    isSubmitting.value = false
  }
}

function refreshResult() {
  if (!submission.value?.id || isRefreshing.value) return
  stopPolling()
  pollAttempts = 0
  pollingStopped.value = false
  void pollResult(submission.value.id)
}

watch(sourceCode, () => {
  if (skipNextDraftSave) {
    skipNextDraftSave = false
    return
  }
  if (draftTimer) window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(saveDraft, 500)
})

onMounted(async () => {
  restoreDraft()
  await loadProblem()
})

onBeforeUnmount(() => {
  stopPolling()
  if (draftTimer) window.clearTimeout(draftTimer)
})
</script>

<template>
  <section class="programming-page">
    <RouterLink class="back-link" to="/student">← 返回我的作业</RouterLink>
    <p v-if="isLoading" role="status">正在加载题目…</p>
    <div v-else-if="error && !problem" class="error" role="alert">加载失败：{{ error }}</div>
    <template v-else-if="problem">
      <header class="hero">
        <h1>{{ problem.title }}</h1>
        <p class="problem-meta">C++17 · {{ problem.time_limit_ms }} ms · {{ problem.memory_limit_mb }} MiB</p>
        <p>{{ problem.statement }}</p>
      </header>

      <div class="problem-grid">
        <article class="panel problem-panel">
          <h2>题目说明</h2>
          <h3>输入</h3><p>{{ problem.input_description }}</p>
          <h3>输出</h3><p>{{ problem.output_description }}</p>
          <h3>公开样例</h3>
          <div v-for="(sample, index) in problem.samples" :key="index" class="sample">
            <span>样例 {{ index + 1 }} 输入</span><pre>{{ sample.input_data }}</pre>
            <span>预期输出</span><pre>{{ sample.expected_output }}</pre>
          </div>
        </article>

        <article class="panel submit-panel">
          <div class="submission-heading">
            <div><h2>编写并提交</h2><p>代码只在点击提交后发送到服务器。</p></div>
            <span>C++17</span>
          </div>
          <div class="editor-tools">
            <p class="hint">{{ sourceByteSize }} / {{ maxSourceBytes }} 字节 · {{ draftMessage || '正在准备本地草稿。' }}</p>
            <button type="button" class="clear-button" @click="clearDraft">清除草稿</button>
          </div>
          <StudentCodeEditor v-model="sourceCode" :disabled="isSubmitting || activeStatus" :max-length="maxSourceBytes" />
          <p class="hint">隐藏测试用例不会展示；提交后会在隔离环境中编译和运行。</p>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <button class="submit-button" type="button" :disabled="isSubmitting || activeStatus" @click="handleSubmit">
            {{ isSubmitting ? '正在提交…' : activeStatus ? '判题进行中…' : '提交并判题' }}
          </button>
          <ProgrammingSubmissionResult v-if="submission" :submission="submission" :polling-stopped="pollingStopped" :is-refreshing="isRefreshing" @refresh="refreshResult" />
        </article>
      </div>
      <ProgrammingSubmissionHistory ref="history" :assignment-id="assignmentId" :latest-result="submission" @current="restoreCurrentSubmission" />
    </template>
  </section>
</template>

<style scoped>
.programming-page { padding: 0; color: var(--ink); }
.back-link { color: var(--muted); text-decoration: none; font-size: 14px; font-weight: 500; display: inline-flex; min-height: 44px; align-items: center; }
.back-link:hover { color: var(--primary); }
.hero { margin: 20px 0 24px; }
.hero h1 { margin: 6px 0 10px; font-size: 28px; }
.hero p { max-width: 760px; color: var(--muted); line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.hero .problem-meta { color: var(--primary); font-size: 14px; margin: 0; }
.problem-grid { display: grid; grid-template-columns: minmax(0,.85fr) minmax(0,1.15fr); gap: 22px; align-items: start; }
.panel { min-width: 0; padding: 24px; color: var(--ink); border: 0; border-radius: var(--radius); background: var(--surface); }
.panel h2, .panel h3 { margin: 0; }
.problem-panel h3 { margin-top: 24px; font-size: 15px; }
.panel p { color: var(--muted); line-height: 1.8; overflow-wrap: anywhere; white-space: pre-wrap; }
.sample { margin-top: 16px; }
.sample span { font-size: 13px; color: var(--muted); }
.sample pre { padding: 14px; border: 0; border-radius: 4px; overflow: auto; background: var(--surface-subtle); color: var(--ink); font: 14px/1.7 Consolas, monospace; }
.submission-heading { display: flex; justify-content: space-between; align-items: start; gap: 16px; flex-wrap: wrap; }
.submission-heading p { margin: 5px 0 0; font-size: 14px; }
.submission-heading > span { padding: 4px 9px; border-radius: 6px; color: var(--primary-hover); background: var(--primary-soft); font-size: 11px; }
.editor-tools { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin: 18px 0 10px; }
.hint { margin: 12px 0 0; color: var(--muted); font-size: 12px; }
.editor-tools .hint { margin: 0; }
.clear-button { flex: none; min-height: 44px; padding: 8px 12px; border: 0; border-radius: 4px; color: var(--muted); background: var(--surface-subtle); font-size: 13px; }
.clear-button:hover { border-color: var(--primary); color: var(--primary); }
.submit-button { min-height: 44px; margin-top: 18px; padding: 10px 18px; border: 0; border-radius: 4px; color: white; background: var(--primary); font-size: 14px; font-weight: 600; }
.submit-button:hover:not(:disabled) { background: var(--primary-hover); }
.error { color: var(--danger); }
@media (max-width: 1150px) { .problem-grid { grid-template-columns: minmax(0,1fr); } }
@media (max-width: 680px) { .panel { padding: 18px; } .hero h1 { font-size: 24px; } }
</style>
