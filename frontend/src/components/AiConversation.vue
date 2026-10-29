<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { askAi, getAiHistory, getStudentAiStatus, getTextAiSettings } from '../api/ai'
import AiAnswer from './AiAnswer.vue'

const props = defineProps({ mode: { type: String, required: true }, contextId: { type: [String, Number], default: '' },
  sourceCode: { type: String, default: '' }, selectedCode: { type: String, default: '' },
  submissionId: { type: Number, default: null }, autoPrompt: { type: String, default: '' } })
const items = ref([]), question = ref(''), loading = ref(true), busy = ref(false), error = ref(''), config = ref(null), remaining = ref(null)
const log = ref(null)
let conversation = crypto.randomUUID(), disposed = false, pollTimer = null
const actions = computed(() => props.mode === 'PROGRAMMING' ? [
  ['understand', '理解题目', '请解释当前题目的输入、输出和公开样例。'],
  ['explain', '解释代码', props.selectedCode ? '请解释我选中的这段代码，并联系完整代码说明它的作用。' : '请解释我当前代码的关键变量和执行过程。'],
  ['debug', '分析错误', '请结合当前代码和已提供的判题结果，分析可能的问题与排查步骤。'],
  ['complexity', '分析复杂度', '请分析当前代码的时间和空间复杂度，并解释依据。'],
  ['hint', '下一步提示', '请根据我现在的代码给出下一步提示。'],
] : props.mode === 'KNOWLEDGE' ? [
  ['understand', '通俗讲解', '请先解释这个知识点解决什么问题，再讲核心步骤。'],
  ['example', '走一个例子', '请用小规模输入一步步演示这个知识点。'],
  ['proof', '正确性与复杂度', '请讲解这个知识点涉及的正确性证明和复杂度分析。'],
  ['compare', '比较相近算法', '请比较这个知识点与最容易混淆的相近算法。'],
  ['practice', '做一道练习', '请围绕这个知识点出一道小练习，先让我回答，再讲解。'],
] : [
  ['teaching', '生成教学建议', '请根据当前班级范围的真实统计，给出优先讲解内容、依据和下一次课的安排。'],
  ['teaching', '分析常见错误', '请根据当前统计中的错误分布，建议排查与课堂讲解的重点，并引用实际数据。'],
  ['teaching', '安排复习练习', '请根据知识点表现与有效样本，设计一次复习课和分层练习安排。'],
])
const available = computed(() => config.value?.configured && config.value?.enabled)
async function load(poll = false) {
  if (pollTimer) clearTimeout(pollTimer)
  if (!poll) loading.value = true
  error.value = ''
  try {
    const [settings, history] = await Promise.all([
      props.mode === 'TEACHING' ? getTextAiSettings() : getStudentAiStatus(),
      getAiHistory(props.mode, props.contextId),
    ])
    if (disposed) return
    config.value = settings; items.value = history.items
    if (items.value.length) conversation = items.value.at(-1).conversation_id
    busy.value = items.value.some(item => item.status === 'PROCESSING')
  } catch (err) { if (!disposed) error.value = err.message }
  finally { if (!disposed) { loading.value = false; if (busy.value) pollTimer = setTimeout(() => load(true), 3000) } }
}
onMounted(async () => { await load(); if (!disposed && props.autoPrompt && !items.value.length && available.value) await send(props.autoPrompt, 'teaching') })
onBeforeUnmount(() => { disposed = true; if (pollTimer) clearTimeout(pollTimer) })
function fresh() {
  conversation = crypto.randomUUID(); items.value = []; error.value = ''; question.value = ''
}
async function send(text = question.value, action = 'question') {
  if (busy.value || loading.value || !available.value || !text.trim()) return
  busy.value = true; error.value = ''
  const pending = { id: 'pending', question: text.trim(), answer: null, status: 'PROCESSING' }
  items.value.push(pending)
  question.value = ''
  try {
    const data = await askAi(props.mode, props.contextId, { conversation_id: conversation,
      question: pending.question, action, ...(props.mode === 'PROGRAMMING' ? {
        source_code: props.sourceCode, selected_code: props.selectedCode, submission_id: props.submissionId,
      } : {}) })
    if (disposed) return
    items.value[items.value.length - 1] = data
    remaining.value = data.remaining_today
    await nextTick()
    log.value?.lastElementChild?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  } catch (err) {
    if (!disposed) { pending.status = 'FAILED'; items.value = items.value.filter(item => item.id !== 'pending'); question.value = pending.question; error.value = err.message }
  } finally { if (!disposed) busy.value = false }
}
</script>
<template>
  <section class="ai-conversation" :aria-busy="busy || loading" aria-label="课程 AI 助教">
    <div class="section-heading"><strong>{{ mode === 'TEACHING' ? 'AI 教学助理' : '课程 AI 助教' }}</strong><button type="button" class="button button-small button-secondary" :disabled="busy || loading" @click="fresh">新对话</button></div>
    <p class="muted ai-context">{{ mode === 'PROGRAMMING' ? (selectedCode ? '已选中代码片段；本轮会同时参考当前草稿与对应判题版本。' : '提问时会发送本题说明、当前草稿及对应判题版本。') : mode === 'TEACHING' ? '依据当前班级范围的真实学习统计生成建议。' : '围绕当前知识点讲解、举例与练习。' }}</p>
    <p v-if="loading" role="status">正在加载助教与对话记录…</p>
    <p v-if="!loading && config && !available" class="notice">{{ mode === 'TEACHING' ? '请先配置并开启文字助教。' : '老师尚未开启课程文字助教。' }} <RouterLink v-if="mode === 'TEACHING'" to="/teacher/ai">前往配置</RouterLink></p>
    <p v-if="error" role="alert" class="notice notice-error">{{ error }} <button v-if="!config" type="button" class="button button-small button-secondary" @click="load">重新加载</button></p>
    <div class="ai-actions"><button v-for="[action, label, prompt] in actions" :key="label" type="button" :disabled="busy || loading || !available" @click="send(prompt, action)">{{ label }}</button></div>
    <div ref="log" class="ai-chat-log" aria-label="对话记录" aria-live="polite" aria-relevant="additions text">
      <p v-if="!items.length && !loading" class="muted">选择一个操作，或直接输入你的问题。</p>
      <article v-for="item in items" :key="item.id" class="ai-turn"><p class="ai-question"><strong>{{ mode === 'TEACHING' ? '教师' : '我' }}</strong>{{ item.question }}</p><AiAnswer v-if="item.answer" :content="item.answer" /><p v-else-if="item.status === 'PROCESSING'" role="status" class="muted">助教正在分析，请稍候…</p><p v-else class="muted">这次请求未完成，可以重新提问。</p></article>
    </div>
    <form class="ai-compose" @submit.prevent="send()"><label :for="`ai-question-${mode}`">继续提问</label><textarea :id="`ai-question-${mode}`" v-model="question" rows="3" maxlength="3000" :disabled="busy || loading || !available" placeholder="写下你想理解的问题…" /><div class="section-heading"><small class="muted">{{ remaining !== null ? `今日剩余 ${remaining} 次` : mode === 'TEACHING' ? '建议可复制后编辑使用' : `每日最多 ${config?.student_daily_limit ?? '—'} 次` }}</small><button type="submit" class="button button-small" :disabled="busy || loading || !available || !question.trim()">{{ busy ? '正在分析…' : '发送问题' }}</button></div></form>
  </section>
</template>
<style scoped>
.ai-conversation { min-width: 0; } .ai-context { font-size: 13px; line-height: 1.7; }
.ai-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.ai-actions button { background: var(--surface-subtle); color: var(--ink); border: 1px solid var(--border); border-radius: 20px; padding: 9px 13px; cursor: pointer; font: inherit; font-size: 13px; }
.ai-actions button:disabled { opacity: .5; cursor: default; }
.ai-chat-log { max-height: 550px; overflow: auto; overscroll-behavior: contain; }
.ai-turn { padding: 12px 0; border-top: 1px solid var(--border); }
.ai-question { background: var(--surface-subtle); padding: 12px 14px; border-radius: 16px 16px 4px 16px; font-size: 14px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.ai-question strong { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; }
.ai-compose { margin-top: 16px; display: grid; gap: 8px; } .ai-compose label { font-weight: 600; font-size: 14px; }
textarea { box-sizing: border-box; width: 100%; resize: vertical; min-height: 90px; background: var(--surface, white); color: var(--ink); border: 1px solid var(--border); border-radius: 12px; padding: 12px; font: inherit; }
</style>
