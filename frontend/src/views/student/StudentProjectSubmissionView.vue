<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import {
  claimTopic,
  getAssignmentTopics,
  getMaterialCheck,
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
const selectedTopicId = ref('')
const zipFile = ref(null)
const materialCheck = ref(null)
const error = ref('')
const success = ref('')
const isLoading = ref(false)
const isSubmitting = ref(false)
const isClaiming = ref(false)
let pollTimer

const manifestForm = ref({
  pptPath: '',
  videoPath: '',
  readmePath: 'README.md',
  sourcePaths: '',
  examplePages: '',
  tests: [
    { inputPath: '', expectedPath: '' },
    { inputPath: '', expectedPath: '' },
    { inputPath: '', expectedPath: '' }
  ]
})

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

async function loadTopics() {
  isLoading.value = true
  error.value = ''
  try {
    const data = await getAssignmentTopics(assignmentId.value)
    topics.value = data.topics
    claim.value = data.claim
  } catch (err) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}

async function submitClaim() {
  if (!selectedTopicId.value) return
  isClaiming.value = true
  error.value = ''
  try {
    claim.value = await claimTopic(assignmentId.value, Number(selectedTopicId.value))
    success.value = '知识点认领成功，现在可以上传作业包。'
  } catch (err) {
    error.value = err.message
  } finally {
    isClaiming.value = false
  }
}

function onFileChange(event) {
  zipFile.value = event.target.files?.[0] ?? null
}

async function pollMaterialCheck(submissionId, attempts = 0) {
  try {
    materialCheck.value = await getMaterialCheck(submissionId)
    if (materialCheck.value.status === 'PENDING' && attempts < 20) {
      pollTimer = window.setTimeout(() => pollMaterialCheck(submissionId, attempts + 1), 2000)
    }
  } catch (err) {
    error.value = err.message
  }
}

async function uploadProject() {
  if (!zipFile.value) {
    error.value = '请选择 ZIP 作业包。'
    return
  }
  isSubmitting.value = true
  error.value = ''
  success.value = ''
  materialCheck.value = null
  try {
    const created = await submitProject(assignmentId.value, zipFile.value, buildManifest())
    success.value = `第 ${created.version} 版作业包已提交，正在检查材料。`
    await pollMaterialCheck(created.submission_id)
  } catch (err) {
    error.value = err.message
  } finally {
    isSubmitting.value = false
  }
}

onMounted(loadTopics)
onBeforeUnmount(() => window.clearTimeout(pollTimer))
</script>

<template>
  <section class="card submission-page">
    <RouterLink class="back-link" to="/student">← 返回我的作业</RouterLink>
    <p class="eyebrow">期末项目作业</p>
    <h1>认领并上传</h1>
    <p>先认领一个知识点，再提交符合命名规范的 ZIP 作业包。</p>

    <p v-if="isLoading" role="status">正在加载知识点…</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="success" class="success" role="status">{{ success }}</p>

    <section v-if="!isLoading && !claim" class="form-section" aria-labelledby="claim-title">
      <h2 id="claim-title">1. 认领知识点</h2>
      <label for="topic">知识点</label>
      <select id="topic" v-model="selectedTopicId">
        <option value="">请选择</option>
        <option v-for="topic in topics" :key="topic.id" :value="topic.id">
          {{ topic.code }} · {{ topic.name }}
        </option>
      </select>
      <button type="button" :disabled="!selectedTopicId || isClaiming" @click="submitClaim">
        {{ isClaiming ? '正在认领…' : '确认认领' }}
      </button>
    </section>

    <section v-else-if="claim" class="form-section" aria-labelledby="upload-title">
      <h2 id="upload-title">2. 上传作业包</h2>
      <p class="claim-summary">已认领：{{ claim.topic.code }} · {{ claim.topic.name }}</p>
      <p class="hint">ZIP 命名：学号_姓名_{{ claim.topic.code }}.zip。材料路径需与 ZIP 内路径完全一致。</p>

      <label for="zip-file">ZIP 作业包</label>
      <input id="zip-file" type="file" accept=".zip,application/zip" @change="onFileChange">

      <div class="field-grid">
        <label>PPT 路径<input v-model="manifestForm.pptPath" placeholder="slides/lesson.pptx"></label>
        <label>视频路径<input v-model="manifestForm.videoPath" placeholder="video/lesson.mp4"></label>
        <label>README 路径<input v-model="manifestForm.readmePath" placeholder="README.md"></label>
        <label>源码路径（逗号或换行分隔）<textarea v-model="manifestForm.sourcePaths" rows="2" placeholder="src/main.cpp" /></label>
        <label>例题所在 PPT 页码（至少 3 页，逗号分隔）<input v-model="manifestForm.examplePages" placeholder="4, 6, 8"></label>
      </div>

      <fieldset>
        <legend>三组测试及预期输出</legend>
        <div v-for="(test, index) in manifestForm.tests" :key="index" class="test-row">
          <input v-model="test.inputPath" :aria-label="`第 ${index + 1} 组测试输入路径`" :placeholder="`tests/case${index + 1}.in`">
          <input v-model="test.expectedPath" :aria-label="`第 ${index + 1} 组预期输出路径`" :placeholder="`tests/case${index + 1}.out`">
        </div>
      </fieldset>

      <button type="button" :disabled="isSubmitting" @click="uploadProject">
        {{ isSubmitting ? '正在上传…' : '上传并检查' }}
      </button>
    </section>

    <section v-if="materialCheck" class="check-result" aria-labelledby="result-title">
      <h2 id="result-title">材料检查结果：{{ materialCheck.status }}</h2>
      <p v-if="materialCheck.status === 'PENDING'">正在后台检查，请稍候。</p>
      <p v-else-if="materialCheck.status === 'VALID'">必交材料路径已通过自动完整性检查。</p>
      <p v-else>材料尚不完整，请根据缺失项修正后重新上传。</p>
      <p v-if="materialCheck.missing_items.length">缺失项：{{ materialCheck.missing_items.join('、') }}</p>
      <p v-if="materialCheck.warnings.length">提示：{{ materialCheck.warnings.join('、') }}</p>
    </section>
  </section>
</template>

<style scoped>
.submission-page { display: grid; gap: 16px; }
.back-link { color: #0d4d3a; text-decoration: none; font-weight: 600; }
.eyebrow { margin: 0; color: #276749; font-size: 14px; font-weight: 700; }
h1, h2 { margin: 0; }
.form-section, .check-result { display: grid; gap: 12px; padding: 20px; border: 1px solid #d7e5dc; border-radius: 10px; }
.claim-summary, .success { margin: 0; color: #17603f; font-weight: 600; }
.hint { margin: 0; color: #667085; font-size: 14px; }
label { display: grid; gap: 6px; color: #344054; font-size: 14px; font-weight: 600; }
input, select, textarea { width: 100%; padding: 9px; border: 1px solid #98b9a5; border-radius: 6px; font: inherit; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
fieldset { display: grid; gap: 8px; margin: 0; padding: 12px; border: 1px solid #d7e5dc; border-radius: 8px; }
legend { padding: 0 4px; color: #344054; font-size: 14px; font-weight: 600; }
.test-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
button { justify-self: start; padding: 9px 14px; border: 0; border-radius: 6px; color: white; background: #0d4d3a; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .6; }
@media (max-width: 680px) { .field-grid, .test-row { grid-template-columns: 1fr; } }
</style>
