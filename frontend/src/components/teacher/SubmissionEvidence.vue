<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ReviewEvidence from './ReviewEvidence.vue'
import VideoAnalysis from './VideoAnalysis.vue'
import { getEvidence, getMaterial } from '../../api/teacher'

const props = defineProps({ submissionId: { type: Number, required: true }, rubricItems: { type: Array, default: () => [] } })
const evidence = ref(null),
  error = ref(''),
  busy = ref(false),
  preview = ref(null)
let generation = 0
const videoElement = ref(null)
let pendingSeek = null
function seekLoaded() {
  if (pendingSeek !== null && videoElement.value) {
    videoElement.value.currentTime = Math.min(pendingSeek, videoElement.value.duration || pendingSeek)
    pendingSeek = null
    videoElement.value.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    videoElement.value.focus()
  }
}
async function seekVideo(seconds) {
  const version = generation
  if (preview.value?.kind !== 'video') {
    const item = evidence.value?.materials.find((m) => m.kind === 'VIDEO')
    if (!item || busy.value) return
    await open(item)
  }
  if (generation !== version || preview.value?.kind !== 'video') return
  pendingSeek = seconds
  await nextTick()
  if (videoElement.value?.readyState >= 1) seekLoaded()
}
const total = (snapshot) => (snapshot?.rubric_scores || []).reduce((sum, item) => sum + Number(item.score), 0).toFixed(2)
const previousScore = (revision, id) => revision.before.rubric_scores.find((item) => item.rubric_item_id === id)?.score
function clearPreview() {
  if (preview.value?.url) URL.revokeObjectURL(preview.value.url)
  preview.value = null
}
watch(
  () => props.submissionId,
  async (id) => {
    const version = ++generation
    evidence.value = null
    error.value = ''
    busy.value = false
    pendingSeek = null
    clearPreview()
    try {
      const data = await getEvidence(id)
      if (version === generation) evidence.value = data
    } catch (err) {
      if (version === generation) error.value = err.message
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  generation++
  clearPreview()
})
async function open(item, download = false) {
  if (busy.value) return
  const version = generation,
    id = props.submissionId
  busy.value = true
  error.value = ''
  clearPreview()
  try {
    const blob = await getMaterial(id, item?.path)
    if (generation !== version) return
    const name = item?.path.split('/').at(-1) || `作业-${id}.zip`
    if (!download && item?.kind === 'VIDEO') {
      preview.value = { url: URL.createObjectURL(blob), kind: 'video', name }
    } else if (
      !download &&
      blob.type.startsWith('text/') &&
      blob.size <= 1024 * 1024
    ) {
      const content = await blob.text()
      if (generation === version)
        preview.value = { kind: 'text', content, name }
    } else {
      const url = URL.createObjectURL(blob),
        link = document.createElement('a')
      link.href = url
      link.download = name
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  } catch (err) {
    if (generation === version) error.value = err.message
  } finally {
    if (generation === version) busy.value = false
  }
}
</script>
<template>
  <section class="evidence-section" aria-label="作业材料与评审记录">
    <h3>作业材料与评审记录</h3>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="!evidence && !error" role="status">正在读取材料清单…</p>
    <template v-if="evidence">
      <p class="muted">
        提交版本 v{{ evidence.version }} ·
        {{
          evidence.is_current ? '当前版本' : '历史版本'
        }}
      </p>
      <section v-if="evidence.answer != null" class="material-preview" aria-label="学生在线答案">
        <h4>在线答案</h4><pre>{{ evidence.answer }}</pre>
      </section>
      <div class="toolbar">
        <button
          v-if="evidence.archive_available"
          type="button"
          class="button button-secondary button-small"
          :disabled="busy"
          @click="open(null, true)"
        >
          下载完整作业包
        </button>
        <span v-if="busy" role="status">正在读取文件，请稍候…</span>
      </div>
      <ul v-if="evidence.materials.length" class="material-list">
        <li v-for="item in evidence.materials" :key="item.path">
          <span
            >{{
              {
                PPT: '课件',
                VIDEO: '视频',
                README: '说明',
                CODE: '代码',
                EXAMPLES: '例题',
                TESTS: '测试材料',
              }[item.kind]
            }}
            · {{ item.path }}</span
          >
          <div class="toolbar">
            <button
              v-if="['VIDEO', 'README', 'CODE', 'TESTS'].includes(item.kind)"
              type="button"
              class="button button-secondary button-small"
              :disabled="busy"
              @click="open(item)"
            >
              {{ item.kind === 'VIDEO' ? '播放视频' : '查看内容' }}
            </button>
            <button
              type="button"
              class="button button-secondary button-small"
              :disabled="busy"
              @click="open(item, true)"
            >
              下载
            </button>
          </div>
        </li>
      </ul>
      <p v-else class="muted">
        暂无可查看的材料，请核对学生的提交情况。
      </p>
      <div v-if="preview" class="material-preview">
        <div class="section-heading">
          <strong>{{ preview.name }}</strong
          ><button
            class="button button-secondary button-small"
            type="button"
            @click="clearPreview"
          >
            关闭预览
          </button>
        </div>
        <video
          ref="videoElement"
          v-if="preview.kind === 'video'"
          :src="preview.url"
          controls
          preload="metadata"
          aria-label="学生微课视频"
          tabindex="0"
          @loadedmetadata="seekLoaded"
        />
        <pre v-else>{{ preview.content }}</pre>
      </div>
      <VideoAnalysis v-if="evidence.materials.some((item) => item.kind === 'VIDEO')" :key="submissionId" :submission-id="submissionId" @seek="seekVideo" />
      <details>
        <summary>
          五人当前评分与评语（{{
            evidence.reviews.filter((r) => r.is_active !== false && r.status === 'SUBMITTED').length
          }}
          / 5 已提交）
        </summary>
        <p v-if="!evidence.reviews.length" class="muted">尚未生成评审任务。</p>
        <article
          v-for="review in evidence.reviews"
          :key="review.id"
          class="review-evidence"
        >
          <strong>{{ review.reviewer_name }} · {{ review.student_no }}</strong>
          <p v-if="review.is_active === false" class="muted">已替补，不计入有效五评 · {{ review.replacement?.reason }} · 新任务 #{{ review.replacement?.new_task_id }}</p>
          <p>{{ review.status === 'SUBMITTED' ? '已提交' : '待完成' }}</p>
          <ul>
            <li v-for="score in review.scores" :key="score.name">
              {{ score.name }}：{{ score.score }} / {{ score.max_score }}
            </li>
          </ul>
          <p class="preserve-lines">{{ review.comment || '暂无评语' }}</p>
          <details v-if="review.revisions?.length" class="review-revisions">
            <summary>评分修改记录（{{ review.revisions.length }} 次）</summary>
            <article v-for="revision in review.revisions" :key="revision.version" class="revision-entry">
              <h4>v{{ revision.version - 1 }} → v{{ revision.version }} · {{ new Date(revision.created_at).toLocaleString('zh-CN') }}</h4>
              <p class="preserve-lines"><strong>修改原因：</strong>{{ revision.reason }}</p>
              <p>总分：{{ total(revision.before) }} → {{ total(revision.after) }}</p>
              <ul>
                <li v-for="item in revision.after.rubric_scores" :key="item.rubric_item_id">
                  {{ item.name }}：{{ previousScore(revision, item.rubric_item_id) }} → {{ item.score }} / {{ item.max_score }}
                </li>
              </ul>
              <p class="preserve-lines"><strong>修改前评语：</strong>{{ revision.before.comment }}</p>
              <p class="preserve-lines"><strong>修改后评语：</strong>{{ revision.after.comment }}</p>
            </article>
          </details>
        </article>
      </details>
      <details v-if="evidence.anomalies.length">
        <summary>异常证据与处理记录</summary>
        <article v-for="(item, index) in evidence.anomalies" :key="index">
          <p>
            {{ { HIGH: '高风险', MEDIUM: '中风险', LOW: '低风险' }[item.risk_level] || '待核对' }} ·
            {{
              { OPEN: '待处理', CONFIRMED: '已确认', DISMISSED: '已驳回' }[
                item.status
              ]
            }}
          </p>
          <ReviewEvidence :evidence="item.evidence_json" :rubric-items="rubricItems" />
          <p>{{ item.resolution_note }}</p>
        </article>
      </details>
      <div v-if="evidence.final_review" class="notice notice-success">
        <strong>复核最终分：{{ evidence.final_review.final_score }}</strong>
        <p>{{ evidence.final_review.reason }}</p>
        <small
          >{{ evidence.final_review.entered_by_name }} ·
          {{
            new Date(evidence.final_review.locked_at).toLocaleString()
          }}</small
        >
      </div>
    </template>
  </section>
</template>
<style scoped>
.evidence-section {
  border-top: 1px solid var(--border);
  padding: 20px 0;
  margin: 18px 0;
  border-radius: 8px;
  min-width: 0;
}
.review-revisions { margin-top: 12px; }
.revision-entry { padding: 12px 16px; margin: 12px 0; border-left: 3px solid var(--primary); background: var(--surface-subtle); border-radius: 0 14px 14px 0; }
.revision-entry h4 { margin: 0 0 10px; }
.material-list {
  list-style: none;
  margin: 12px 0;
  padding: 0;
}
.material-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.material-list li > span {
  overflow-wrap: anywhere;
  min-width: 0;
}
.material-list .toolbar {
  flex-shrink: 0;
}
.material-preview {
  background: var(--canvas, #f7f9fa);
  padding: 12px;
  border-radius: 18px;
}
video {
  display: block;
  border-radius: 14px;
  background: var(--code-bg);
  width: 100%;
  max-height: 420px;
  margin-top: 12px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 360px;
  overflow: auto;
  font:
    13px/1.7 Consolas,
    monospace;
}
details {
  margin-top: 16px;
}
summary {
  cursor: pointer;
  padding: 8px 0;
  font-weight: 600;
}
.review-evidence {
  border-top: 1px solid var(--border);
  padding: 14px 0;
}
.preserve-lines {
  white-space: pre-wrap;
}
@media (max-width: 640px) {
  .material-list li {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
