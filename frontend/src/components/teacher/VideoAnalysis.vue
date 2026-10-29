<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { cancelVideoAnalysis, getAiVideoSettings, getVideoAnalyses, startVideoAnalysis } from '../../api/teacher'

const props = defineProps({ submissionId: { type: Number, required: true } })
const emit = defineEmits(['seek'])
const config = ref(null), runs = ref([]), error = ref(''), busy = ref(false), loading = ref(true)
const current = computed(() => runs.value[0])
const active = computed(() => ['QUEUED', 'PROCESSING'].includes(current.value?.status))
const result = computed(() => current.value?.status === 'SUCCEEDED' ? current.value.result_json : null)
const labels = { QUEUED: '等待分析', PROCESSING: '正在分析', SUCCEEDED: '分析完成', FAILED: '分析失败', CANCELLED: '已停止' }
let timer, disposed = false
const timestamp = (seconds) => `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
function schedule() {
  clearTimeout(timer)
  if (active.value && !disposed) timer = setTimeout(refresh, 3000)
}
async function refresh() {
  error.value = ''
  try {
    if (!config.value) {
      const settings = await getAiVideoSettings()
      if (disposed) return
      config.value = settings
    }
    const data = await getVideoAnalyses(props.submissionId)
    if (disposed) return
    runs.value = data.runs
    schedule()
  } catch (err) { if (!disposed) error.value = err.message }
}
onMounted(async () => {
  try {
    const [settings, data] = await Promise.all([getAiVideoSettings(), getVideoAnalyses(props.submissionId)])
    if (disposed) return
    config.value = settings; runs.value = data.runs; schedule()
  } catch (err) { if (!disposed) error.value = err.message }
  finally { if (!disposed) loading.value = false }
})
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
async function start() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await startVideoAnalysis(props.submissionId, !!current.value); await refresh() }
  catch (err) { if (!disposed) error.value = err.message }
  finally { if (!disposed) busy.value = false }
}
async function cancel() {
  busy.value = true; error.value = ''
  try { await cancelVideoAnalysis(props.submissionId, current.value.id); await refresh() }
  catch (err) { if (!disposed) error.value = err.message }
  finally { if (!disposed) busy.value = false }
}
</script>

<template>
  <section class="video-analysis" aria-label="AI 视频辅助分析">
    <div class="section-heading"><h4>AI 视频辅助分析</h4><span v-if="current" class="badge">{{ labels[current.status] }}</span></div>
    <p class="muted">根据视频画面与讲解声音，按本作业评分表生成建议和时间点证据。</p>
    <p v-if="loading" role="status">正在加载分析记录…</p>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }} <button type="button" class="button button-small button-secondary" @click="refresh">重试加载</button></p>
    <p v-if="!loading && config && (!config.configured || !config.enabled)">请先在 <RouterLink to="/teacher/ai-video">视频辅助评阅</RouterLink> 填写密钥并开启分析。</p>
    <template v-if="current">
      <p class="muted">{{ current.provider === 'qwen' ? '通义千问' : 'Gemini' }} · {{ current.model }} · {{ new Date(current.created_at).toLocaleString('zh-CN') }}</p>
      <p v-if="active" role="status">{{ current.status === 'QUEUED' ? '任务已创建，等待处理视频。' : current.progress_json?.total_clips ? `已分析 ${current.progress_json.completed_clips} / ${current.progress_json.total_clips} 个片段${current.progress_json.completed_clips === current.progress_json.total_clips ? '，正在汇总评分建议…' : '…'}` : '正在读取并处理视频…' }}</p>
      <p v-if="current.status === 'FAILED'" class="notice notice-error" role="alert">{{ current.error_message }}</p>
    </template>
    <div class="toolbar">
      <button v-if="!active" type="button" class="button button-small" :disabled="busy || loading || !config?.configured || !config?.enabled" @click="start">{{ busy ? '正在创建任务…' : current ? '重新分析视频' : '分析视频' }}</button>
      <button v-else type="button" class="button button-small button-secondary" :disabled="busy" @click="cancel">停止分析</button>
      <RouterLink to="/teacher/ai-video">连接设置</RouterLink>
    </div>
    <small class="muted">点击分析会将本作品的视频发送给配置的模型服务，调用费用由密钥账户承担。</small>
    <div v-if="result" class="analysis-result">
      <h5>内容概述与建议</h5><p class="preserve-lines">{{ result.summary }}</p>
      <article v-for="item in result.assessments" :key="item.rubric_item_id">
        <div class="section-heading"><strong>{{ item.name }}</strong><span>建议 {{ item.suggested_score }} / {{ item.max_score }}</span></div>
        <p class="preserve-lines">{{ item.rationale }}</p><small class="muted">模型自评置信度 {{ Math.round(item.confidence * 100) }}%</small>
        <ul v-if="item.evidence.length" class="analysis-evidence"><li v-for="(e, index) in item.evidence" :key="index"><button type="button" class="time-link" :aria-label="`回看 ${timestamp(e.start_seconds)}：${e.description}`" @click="emit('seek', e.start_seconds)">{{ timestamp(e.start_seconds) }}–{{ timestamp(e.end_seconds) }}</button><span>{{ e.description }}</span></li></ul>
        <p v-else class="muted">此项未提供可定位的视频证据。</p>
      </article>
      <p class="muted">教师可结合原视频与其他材料填写最终评分。</p>
    </div>
    <details v-if="runs.length > 1"><summary>历史分析（{{ runs.length - 1 }}）</summary><article v-for="run in runs.slice(1)" :key="run.id"><p>{{ new Date(run.created_at).toLocaleString('zh-CN') }} · {{ run.model }} · {{ labels[run.status] }}</p><p v-if="run.error_message">{{ run.error_message }}</p><template v-if="run.result_json"><p class="preserve-lines">{{ run.result_json.summary }}</p><p v-for="item in run.result_json.assessments" :key="item.rubric_item_id">{{ item.name }}：{{ item.suggested_score }} / {{ item.max_score }} · {{ item.rationale }}</p></template></article></details>
  </section>
</template>

<style scoped>
.video-analysis { margin: 20px 0; padding: 20px; border: 1px solid var(--border); border-radius: 20px; background: var(--surface, white); }
h4 { margin: 0; } h5 { font-size: 15px; margin: 18px 0 8px; }
p { line-height: 1.7; } small { display: block; line-height: 1.6; margin-top: 10px; }
.preserve-lines { white-space: pre-wrap; overflow-wrap: anywhere; }
.analysis-result article, details article { border-top: 1px solid var(--border); padding: 18px 0 8px; margin-top: 16px; }
.analysis-evidence { list-style: none; padding: 0; display: grid; gap: 12px; }
.analysis-evidence li { display: flex; gap: 12px; align-items: baseline; line-height: 1.6; }
.time-link { border: 0; border-radius: 6px; background: var(--surface-subtle); color: var(--primary); padding: 4px 6px; font: inherit; cursor: pointer; white-space: nowrap; }
details { margin-top: 18px; } summary { cursor: pointer; }
@media (max-width: 640px) { .video-analysis { padding: 16px; } .analysis-evidence li { flex-direction: column; gap: 4px; } }
</style>
