<script setup>
import AssignmentArtwork from '../../components/AssignmentArtwork.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import ProjectSubmissionHistory from '../../components/student/ProjectSubmissionHistory.vue'
import { emptyProjectForm, inspectProjectArchive } from '../../utils/projectArchive'

import {
  claimTopic,
  getAssignmentTopics,
  getMaterialCheck,
  getCurrentProjectSubmission,
  submitProject
} from '../../api/student/projectSubmissions'

const props = defineProps({
  assignmentId: {
    type: String,
    required: true
  }
})

const assignmentId = computed(() => Number(props.assignmentId))
const topics = ref([])
const claim = ref(null)
const selectedChapter = ref('')
const selectedTopicId = ref('')
const chapters = computed(() => [...new Set(topics.value.map((topic) => topic.chapter))])
const chapterTopics = computed(() => topics.value.filter((topic) => topic.chapter === selectedChapter.value))
const selectedTopic = computed(() => chapterTopics.value.find((topic) => String(topic.id) === String(selectedTopicId.value)))
watch(selectedChapter, () => { selectedTopicId.value = '' })
const zipFile = ref(null)
const materialCheck = ref(null)
const assignment = ref(null)
const currentSubmission = ref(null)
const checkError = ref('')
const isRefreshing = ref(false)
const pollingStopped = ref(false)
const now = ref(Date.now())
const error = ref('')
const success = ref('')
const isLoading = ref(false)
const isSubmitting = ref(false)
const isClaiming = ref(false)
const isInspecting = ref(false)
const archiveMessage = ref('')
const archiveNotices = ref([])
const archiveCandidates = ref({ pptPath: [], videoPath: [], readmePath: [] })
let archiveRequest = 0
let pollTimer
let checkRequest = 0
let pageRequest = 0
const clockTimer = window.setInterval(() => { now.value = Date.now() }, 1000)
const deadlinePassed = computed(() => assignment.value?.submit_deadline &&
  new Date(assignment.value.submit_deadline).getTime() <= now.value)
const canSubmit = computed(() => assignment.value?.can_submit && !deadlinePassed.value)
const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN') : '未设置'
const materialStatusLabel = (status) => ({ VALID: '通过', INVALID: '未通过', PENDING: '检查中' }[status] || status)

function stopPolling() {
  window.clearTimeout(pollTimer)
  checkRequest++
  isRefreshing.value = false
}

const manifestForm = ref({ ...emptyProjectForm(), readmePath: 'README.md' })

function resetArchive() {
  archiveRequest++
  isInspecting.value = false
  archiveMessage.value = ''
  archiveNotices.value = []
  archiveCandidates.value = { pptPath: [], videoPath: [], readmePath: [] }
  manifestForm.value = { ...emptyProjectForm(), readmePath: 'README.md' }
}

function normalisePaths(value) {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)
}

function buildManifest() {
  const pages = manifestForm.value.examplePages
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value) && value > 0)
  return {
    ppt_path: manifestForm.value.pptPath.trim(),
    video_path: manifestForm.value.videoPath.trim(),
    examples: [{ location: 'PPT', pages }],
    source_paths: normalisePaths(manifestForm.value.sourcePaths),
    tests: manifestForm.value.tests.map((test) => ({
      input_path: test.inputPath.trim(),
      expected_path: test.expectedPath.trim()
    })),
    readme_path: manifestForm.value.readmePath.trim()
  }
}

async function loadPage() {
  const request = ++pageRequest
  stopPolling()
  assignment.value = null
  currentSubmission.value = null
  materialCheck.value = null
  claim.value = null
  topics.value = []
  selectedChapter.value = ''
  selectedTopicId.value = ''
  zipFile.value = null
  resetArchive()
  isSubmitting.value = false
  isClaiming.value = false
  checkError.value = ''
  success.value = ''
  isLoading.value = true
  error.value = ''
  try {
    const [data, view] = await Promise.all([
      getAssignmentTopics(assignmentId.value), getCurrentProjectSubmission(assignmentId.value),
    ])
    if (request !== pageRequest) return
    topics.value = data.topics
    claim.value = data.claim
    assignment.value = view
    currentSubmission.value = view.submission
    if (view.submission) void pollMaterialCheck(view.submission.id)
  } catch (err) {
    if (request === pageRequest) error.value = err.message
  } finally {
    if (request === pageRequest) isLoading.value = false
  }
}

async function submitClaim() {
  if (!selectedTopic.value || !canSubmit.value || isClaiming.value) return
  isClaiming.value = true
  const request = pageRequest
  error.value = ''
  try {
    const result = await claimTopic(assignmentId.value, selectedTopic.value.id)
    if (request !== pageRequest) return
    claim.value = result
    success.value = '知识点认领成功，现在可以上传作业包。'
  } catch (err) {
    if (request === pageRequest) error.value = err.message
  } finally {
    if (request === pageRequest) isClaiming.value = false
  }
}

async function onFileChange(event) {
  const file = event.target.files?.[0] ?? null
  zipFile.value = file
  resetArchive()
  if (!file) return
  const request = archiveRequest
  manifestForm.value = emptyProjectForm()
  isInspecting.value = true
  try {
    const data = file.arrayBuffer ? await file.arrayBuffer() : await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = () => reject(new Error('无法读取所选文件'))
      reader.readAsArrayBuffer(file)
    })
    const result = await inspectProjectArchive(data)
    if (request !== archiveRequest) return
    manifestForm.value = result.form
    archiveCandidates.value = result.candidates
    archiveNotices.value = result.notices
    archiveMessage.value = result.manifestUsed
      ? '已读取包内清单并识别材料，请核对后提交。'
      : '已自动识别材料路径和同名测试用例，请核对并补充例题页码。'
  } catch (err) {
    if (request !== archiveRequest) return
    archiveMessage.value = '自动识别未完成，可以手动填写材料清单。'
    archiveNotices.value = [err.message || '请确认文件为可正常打开的 ZIP，且未加密。']
  } finally {
    if (request === archiveRequest) isInspecting.value = false
  }
}

async function pollMaterialCheck(submissionId, attempts = 0, request = ++checkRequest) {
  window.clearTimeout(pollTimer)
  isRefreshing.value = true
  checkError.value = ''
  pollingStopped.value = false
  try {
    const result = await getMaterialCheck(submissionId)
    if (request !== checkRequest || submissionId !== currentSubmission.value?.id) return
    materialCheck.value = result
    if (result.status === 'PENDING') {
      if (attempts < 20) {
        pollTimer = window.setTimeout(() => pollMaterialCheck(submissionId, attempts + 1, request), 2000)
      } else {
        pollingStopped.value = true
      }
    }
  } catch (err) {
    if (request === checkRequest) {
      checkError.value = err.message
      pollingStopped.value = true
    }
  } finally {
    if (request === checkRequest) isRefreshing.value = false
  }
}

async function refreshCurrentSubmission() {
  const request = ++pageRequest
  stopPolling()
  isRefreshing.value = true
  checkError.value = ''
  pollingStopped.value = false
  try {
    const view = await getCurrentProjectSubmission(assignmentId.value)
    if (request !== pageRequest) return
    if (view.submission?.id !== currentSubmission.value?.id) materialCheck.value = null
    assignment.value = view
    currentSubmission.value = view.submission
    if (view.submission) await pollMaterialCheck(view.submission.id)
  } catch (err) {
    if (request === pageRequest) checkError.value = err.message
  } finally {
    if (request === pageRequest) isRefreshing.value = false
  }
}

async function uploadProject() {
  if (isInspecting.value) return
  if (!canSubmit.value) {
    error.value = '作业已截止或当前阶段不允许上传，已有提交仍可查看。'
    return
  }
  if (!zipFile.value) {
    error.value = '请选择 ZIP 作业包。'
    return
  }
  isSubmitting.value = true
  error.value = ''
  success.value = ''
  stopPolling()
  const request = ++pageRequest
  try {
    const created = await submitProject(assignmentId.value, zipFile.value, buildManifest())
    if (request !== pageRequest) return
    currentSubmission.value = { id: created.submission_id, version: created.version, status: 'PENDING' }
    materialCheck.value = null
    success.value = `第 ${created.version} 版作业包已提交。`
    await pollMaterialCheck(created.submission_id)
  } catch (err) {
    if (request !== pageRequest) return
    error.value = err.code === 'INVALID_STATE'
      ? '作业已截止或当前阶段不允许上传，本次未提交成功，已有版本保持不变。'
      : err.message
    isSubmitting.value = false
    await refreshCurrentSubmission()
  } finally {
    if (request === pageRequest) isSubmitting.value = false
  }
}

watch(assignmentId, loadPage, { immediate: true })
onBeforeUnmount(() => {
  stopPolling()
  pageRequest++
  archiveRequest++
  window.clearInterval(clockTimer)
})
</script>

<template>
  <section class="card submission-page">
    <RouterLink class="back-link" to="/student">← 返回我的作业</RouterLink>
    <header class="project-intro"><div><p class="eyebrow">期末项目作业</p>
    <h1>认领并上传</h1>
    <p>先选择所属大章节和知识点，确认认领后上传 ZIP 作业包。</p>
    </div><figure v-if="assignment"><AssignmentArtwork :assignment="{ title: claim?.topic?.name || assignment.title, type: 'FINAL_PROJECT' }" /><figcaption>算法主题插画 · 以认领知识点要求为准</figcaption></figure></header>
    <template v-if="assignment">
      <p>{{ assignment.title }} · 提交截止：{{ formatTime(assignment.submit_deadline) }}</p>
      <p v-if="!canSubmit" class="hint" role="status">{{ deadlinePassed ? '作业已截止。' : '当前阶段不允许上传。' }}已有提交和材料检查结果仍可查看。</p>
      <button type="button" :disabled="isRefreshing || isSubmitting || isClaiming" @click="refreshCurrentSubmission">{{ isRefreshing ? '正在刷新…' : '刷新提交状态' }}</button>
    </template>

    <p v-if="isLoading" role="status">正在加载知识点…</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="success" class="success" role="status">{{ success }}</p>
    <button v-if="!assignment && !isLoading" type="button" @click="loadPage">重试加载作业</button>

    <section v-if="assignment && canSubmit && !isLoading && !claim" class="form-section" aria-labelledby="claim-title">
      <h2 id="claim-title">1. 认领知识点</h2>
      <p v-if="!topics.length" class="hint" role="status">暂无可选知识点，请联系教师补充课程目录。</p>
      <div class="field-grid">
        <label for="chapter">所属大章节
          <select id="chapter" v-model="selectedChapter" :disabled="isClaiming || !topics.length">
            <option value="">请选择所属大章节</option>
            <option v-for="chapter in chapters" :key="chapter" :value="chapter">{{ chapter }}</option>
          </select>
        </label>
        <label for="topic">知识点
          <select id="topic" v-model="selectedTopicId" :disabled="!selectedChapter || isClaiming" aria-describedby="topic-description">
            <option value="">{{ selectedChapter ? '请选择知识点' : '请先选择所属大章节' }}</option>
            <option v-for="topic in chapterTopics" :key="topic.id" :value="topic.id">
              {{ topic.code }} · {{ topic.name }}
            </option>
          </select>
        </label>
      </div>
      <div id="topic-description" class="topic-description" aria-live="polite">
        <template v-if="selectedTopic">
          <h3>知识内容</h3>
          <p>{{ selectedTopic.description || '该知识点暂无内容说明，请向教师确认具体要求。' }}</p>
        </template>
        <p v-else class="hint">选择知识点后，可查看对应的知识内容与例题方向。</p>
      </div>
      <button type="button" :disabled="!selectedTopic || isClaiming" @click="submitClaim">
        {{ isClaiming ? '正在认领…' : '确认认领' }}
      </button>
    </section>

    <section v-else-if="claim" class="form-section" aria-labelledby="upload-title">
      <h2 id="upload-title">2. 上传作业包</h2>
      <p class="claim-summary">已认领：{{ claim.topic.chapter }} / {{ claim.topic.code }} · {{ claim.topic.name }}</p>
      <div v-if="claim.topic.description" class="topic-description">
        <h3>知识内容</h3>
        <p>{{ claim.topic.description }}</p>
      </div>
      <p class="hint">ZIP 命名：学号_姓名_{{ claim.topic.code }}.zip。选择后自动识别材料路径与同名 .in/.out 测试，所有结果均可修改。例题页码可手动填写，或由包内 manifest.json 清单提供。</p>

      <fieldset class="upload-fields" :disabled="!canSubmit || isSubmitting">
      <label for="zip-file">ZIP 作业包</label>
      <input id="zip-file" type="file" accept=".zip,application/zip" aria-describedby="archive-status" @change="onFileChange">
      <div id="archive-status" class="archive-status" :aria-busy="isInspecting" aria-live="polite" role="status">
        <p v-if="isInspecting" class="hint">正在读取 ZIP 并识别材料…</p>
        <template v-else-if="archiveMessage">
          <p class="hint">{{ archiveMessage }}</p>
          <ul v-if="archiveNotices.length"><li v-for="notice in archiveNotices" :key="notice">{{ notice }}</li></ul>
        </template>
      </div>

      <fieldset class="material-fields" :disabled="isInspecting">
      <legend class="hint">材料清单（可修改）</legend>
      <div v-if="Object.values(archiveCandidates).some((paths) => paths.length > 1)" class="field-grid">
        <template v-for="(label, field) in { pptPath: 'PPT', videoPath: '视频', readmePath: 'README' }" :key="field">
          <label v-if="archiveCandidates[field].length > 1">选择{{ label }}文件
            <select v-model="manifestForm[field]" :aria-label="`选择${label}文件`">
              <option value="">请选择文件</option>
              <option v-for="path in archiveCandidates[field]" :key="path" :value="path">{{ path }}</option>
            </select>
          </label>
        </template>
      </div>
      <div class="field-grid">
        <label>PPT 路径<input v-model="manifestForm.pptPath" placeholder="slides/lesson.pptx"></label>
        <label>视频路径<input v-model="manifestForm.videoPath" placeholder="video/lesson.mp4"></label>
        <label>README 路径<input v-model="manifestForm.readmePath" placeholder="README.md"></label>
        <label>源码路径（逗号或换行分隔）<textarea v-model="manifestForm.sourcePaths" rows="2" placeholder="src/main.cpp" /></label>
        <label>例题所在 PPT 页码（至少 3 页，逗号分隔）<input v-model="manifestForm.examplePages" placeholder="4, 6, 8"></label>
      </div>

      <fieldset>
        <legend>测试及预期输出（至少三组）</legend>
        <div v-for="(test, index) in manifestForm.tests" :key="index" class="test-row">
          <input v-model="test.inputPath" :aria-label="`第 ${index + 1} 组测试输入路径`" :placeholder="`tests/case${index + 1}.in`">
          <input v-model="test.expectedPath" :aria-label="`第 ${index + 1} 组预期输出路径`" :placeholder="`tests/case${index + 1}.out`">
        </div>
      </fieldset>
      </fieldset>
      </fieldset>

      <button type="button" :disabled="isSubmitting || isInspecting || !canSubmit" @click="uploadProject">
        {{ isSubmitting ? '正在上传…' : isInspecting ? '正在识别材料…' : '上传并检查' }}
      </button>
    </section>

    <section v-if="currentSubmission" class="check-result" aria-labelledby="result-title">
      <h2 id="result-title">当前提交：第 {{ currentSubmission.version }} 版</h2>
      <p v-if="currentSubmission.submitted_at">提交时间：{{ formatTime(currentSubmission.submitted_at) }}</p>
      <p v-if="isRefreshing" role="status">正在读取材料检查结果…</p>
      <p v-if="checkError" class="error" role="alert">材料检查结果加载失败：{{ checkError }}，请点击“刷新提交状态”重试。</p>
      <p v-if="pollingStopped && materialCheck?.status === 'PENDING'" class="hint" role="status">材料仍在检查中，自动刷新已停止，请点击“刷新提交状态”继续查询。</p>
      <template v-if="materialCheck">
      <h3>材料检查结果：{{ materialStatusLabel(materialCheck.status) }}</h3>
      <p v-if="materialCheck.status === 'PENDING'">正在后台检查，请稍候。</p>
      <p v-else-if="materialCheck.status === 'VALID'">必交材料路径已通过自动完整性检查。</p>
      <p v-else>材料尚不完整，请根据缺失项修正后重新上传。</p>
      <p v-if="materialCheck.missing_items.length">缺失项：{{ materialCheck.missing_items.join('、') }}</p>
      <p v-if="materialCheck.warnings.length">提示：{{ materialCheck.warnings.join('、') }}</p>
      </template>
    </section>
    <p v-else-if="assignment && !isLoading" class="hint">当前没有已提交的作业包。</p>
    <p v-if="checkError && !currentSubmission" class="error" role="alert">提交状态加载失败：{{ checkError }}，请刷新重试。</p>
    <ProjectSubmissionHistory v-if="assignment" :key="assignmentId" :assignment-id="assignmentId" :latest-submission="currentSubmission" :latest-check="materialCheck" />
  </section>
</template>

<style scoped>
.submission-page { display: grid; grid-template-columns: minmax(0,1fr); gap: 16px; }
.project-intro { display: grid; grid-template-columns: minmax(0,1fr) 300px; align-items: center; gap: 28px; }
.project-intro h1 { margin-top: 12px; font-size: 32px; }
.project-intro p { color: var(--muted); line-height: 1.8; }
.project-intro figure { margin: 0; background: var(--art-gradient); border-radius: 24px 64px 24px 24px; padding: 12px; }
.project-intro :deep(svg) { width: 100%; height: 160px; display: block; }
.project-intro figcaption { font-size: 12px; color: var(--muted); text-align: center; }
.submission-page > *, .form-section > *, .check-result > * { min-width: 0; }
.back-link { width: fit-content; display: inline-flex; align-items: center; min-height: 32px; color: var(--muted); font-size: 12px; text-decoration: none; }
.back-link:hover { color: var(--primary); }
.eyebrow { margin: 0; color: var(--primary); font-size: 12px; font-weight: 600; }
h1, h2 { margin: 0; }
.form-section, .check-result { display: grid; grid-template-columns: minmax(0,1fr); gap: 16px; padding: 24px; border: 0; background: var(--surface-subtle); border-radius: 24px; }
.check-result { background: var(--surface-subtle); }
.claim-summary, .success { margin: 0; color: var(--success); font-weight: 600; }
.topic-description { overflow-wrap: anywhere; }
.topic-description h3 { margin: 0 0 8px; font-size: 15px; }
.topic-description p { margin: 0; line-height: 1.8; }
.hint { margin: 0; color: var(--muted); font-size: 13px; }
.submission-page > p { margin-bottom: 0; color: var(--muted); }
.submission-page > .error, .error { color: var(--danger); }
.submission-page > .success { color: var(--success); }
.field-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 18px; }
fieldset { display: grid; gap: 12px; margin: 0; padding: 16px; border: 1px solid var(--border); border-radius: 8px; }
input[type=file] { background: var(--surface-subtle); border-style: dashed; padding: 16px; }
input[type=file]::file-selector-button { margin-right: 12px; padding: 7px 12px; border: 1px solid var(--input-border); background: var(--surface); color: var(--ink); border-radius: 6px; cursor: pointer; }
.test-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.upload-fields { padding: 0; border: 0; }
.material-fields { padding: 0; border: 0; min-width: 0; }
.archive-status:empty { display: none; }
.archive-status ul { margin: 8px 0 0; padding-left: 20px; color: var(--muted); font-size: 13px; line-height: 1.8; }
button { justify-self: start; min-height: 44px; padding: 9px 15px; border: 1px solid var(--primary); border-radius: 14px; color: white; background: var(--primary); font-size: 13px; font-weight: 550; }
button:hover:not(:disabled) { background: var(--primary-hover); }
@media (max-width: 680px) { .project-intro, .field-grid, .test-row { grid-template-columns: minmax(0,1fr); } .project-intro figure { max-width: 100%; } .form-section, .check-result { padding: 16px; } }
</style>
