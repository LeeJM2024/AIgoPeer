<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { getEvidence, getMaterial } from '../../api/teacher'

const props = defineProps({ submissionId: { type: Number, required: true } })
const evidence = ref(null),
  error = ref(''),
  busy = ref(false),
  preview = ref(null)
let generation = 0
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
  <section class="evidence-section" aria-label="原始材料与评分证据">
    <h3>原始材料与评分证据</h3>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="!evidence && !error" role="status">正在读取材料清单…</p>
    <template v-if="evidence">
      <p class="muted">
        提交版本 v{{ evidence.version }} ·
        {{
          evidence.is_current ? '当前版本' : '历史版本'
        }}。材料完整性检查不代表内容质量已通过。
      </p>
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
        此提交没有材料清单。请核对上传记录；旧演示记录可能只有评分数据。
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
          v-if="preview.kind === 'video'"
          :src="preview.url"
          controls
          preload="metadata"
          aria-label="学生微课视频"
        />
        <pre v-else>{{ preview.content }}</pre>
      </div>
      <details>
        <summary>
          五人原始评分与评语（{{
            evidence.reviews.filter((r) => r.status === 'SUBMITTED').length
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
          <p>{{ review.status === 'SUBMITTED' ? '已提交' : '待完成' }}</p>
          <ul>
            <li v-for="score in review.scores" :key="score.name">
              {{ score.name }}：{{ score.score }} / {{ score.max_score }}
            </li>
          </ul>
          <p class="preserve-lines">{{ review.comment || '暂无评语' }}</p>
        </article>
      </details>
      <details v-if="evidence.anomalies.length">
        <summary>异常证据与处理记录</summary>
        <article v-for="(item, index) in evidence.anomalies" :key="index">
          <p>
            {{ item.risk_level }} ·
            {{
              { OPEN: '待处理', CONFIRMED: '已确认', DISMISSED: '已驳回' }[
                item.status
              ]
            }}
          </p>
          <pre>{{ JSON.stringify(item.evidence_json, null, 2) }}</pre>
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
  border: 1px solid var(--border);
  padding: 16px;
  margin: 18px 0;
  border-radius: 8px;
  min-width: 0;
}
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
  background: var(--canvas);
  padding: 12px;
}
video {
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
