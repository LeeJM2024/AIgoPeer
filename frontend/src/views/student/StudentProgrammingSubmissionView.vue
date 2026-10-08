<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import StudentCodeEditor from '../../components/student/StudentCodeEditor.vue'
import ProgrammingSubmissionResult from '../../components/student/ProgrammingSubmissionResult.vue'
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
let pollTimer = null
let draftTimer = null
let pollAttempts = 0
let skipNextDraftSave = false

const draftStorageKey = computed(() => `algopeer:programming-draft:${props.assignmentId}`)
const submissionStorageKey = computed(() => `algopeer:programming-submission:${props.assignmentId}`)
const sourceByteSize = computed(() => new Blob([sourceCode.value]).size)
const activeStatus = computed(() => ['QUEUED', 'RUNNING'].includes(submission.value?.status))

function stopPolling() {
  if (pollTimer) window.clearTimeout(pollTimer)
  pollTimer = null
}

function restoreDraft() {
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
    window.localStorage.removeItem(draftStorageKey.value)
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

function persistSubmissionId(submissionId) {
  try {
    window.localStorage.setItem(submissionStorageKey.value, String(submissionId))
  } catch {
    // A result can still be inspected during the current page session.
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

async function restoreSubmission() {
  try {
    const submissionId = window.localStorage.getItem(submissionStorageKey.value)
    if (submissionId) await pollResult(submissionId)
  } catch {
    // No previous submission is a normal first-visit state.
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
    persistSubmissionId(created.submission_id)
    pollAttempts = 0
    void pollResult(created.submission_id)
  } catch (err) {
    error.value = err.message
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
  await Promise.all([loadProblem(), restoreSubmission()])
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
        <p class="eyebrow">编程题 · C++17 · {{ problem.time_limit_ms }} ms · {{ problem.memory_limit_mb }} MiB</p>
        <h1>{{ problem.title }}</h1>
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
    </template>
  </section>
</template>

<style scoped>
.programming-page { max-width: 1160px; margin: 0 auto; padding: 16px 0 24px; color: #e8f2ed; }.back-link { color: #b8e5c7; text-decoration: none; font-size: 14px; font-weight: 700; }.hero { margin: 28px 0 20px; }.hero h1 { margin: 6px 0; font-size: clamp(26px, 4vw, 34px); }.hero p { max-width: 720px; color: #c5dbcf; line-height: 1.65; }.eyebrow { margin: 0; color: #9fcbb0; font-size: 13px; font-weight: 700; }.problem-grid { display: grid; grid-template-columns: minmax(260px, .85fr) minmax(0, 1.15fr); gap: 18px; }.panel { padding: 22px; border: 1px solid #35634e; border-radius: 12px; background: #103d2e; box-shadow: 0 12px 28px #031c1433; }.panel h2, .panel h3 { margin: 0; }.problem-panel h3 { margin-top: 22px; font-size: 15px; }.panel p { color: #c5dbcf; line-height: 1.55; }.sample { margin-top: 14px; }.sample span { color: #a8d5b8; font-size: 13px; }.sample pre { overflow: auto; padding: 10px; border-radius: 6px; background: #09281e; color: #dcfce7; }.submission-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }.submission-heading p { margin: 5px 0 0; font-size: 13px; }.submission-heading span { padding: 4px 8px; border-radius: 999px; color: #c6f6d5; background: #1d6247; font-size: 12px; }.editor-tools { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 18px 0 8px; }.hint { margin: 0; color: #9fcbb0; font-size: 13px; }.clear-button { flex: none; border: 1px solid #5f9777; border-radius: 7px; padding: 7px 10px; color: #d7f5e1; background: transparent; cursor: pointer; }.submit-button { margin-top: 16px; border: 0; border-radius: 7px; padding: 10px 15px; color: #06271b; background: #b8e5c7; font-weight: 700; cursor: pointer; }.submit-button:disabled { cursor: not-allowed; opacity: .65; }.error { color: #fecaca; } @media (max-width: 760px) { .programming-page { padding-top: 8px; }.problem-grid { grid-template-columns: 1fr; }.editor-tools { align-items: flex-start; flex-direction: column; } }
</style>
