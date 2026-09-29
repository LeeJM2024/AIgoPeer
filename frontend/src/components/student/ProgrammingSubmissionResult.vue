<script setup>
import { computed } from 'vue'

const props = defineProps({
  submission: { type: Object, required: true },
  pollingStopped: { type: Boolean, default: false },
  isRefreshing: { type: Boolean, default: false }
})

const emit = defineEmits(['refresh'])
const activeStatus = computed(() => ['QUEUED', 'RUNNING'].includes(props.submission.status))
const statusLabel = (value) => ({
  QUEUED: '排队中', RUNNING: '判题中', AC: '通过', WA: '答案错误',
  TLE: '超出时间限制', RE: '运行错误', CE: '编译错误', SYSTEM_ERROR: '判题系统异常'
}[value] ?? value)
</script>

<template>
  <section class="result" :class="`result--${submission.status}`" aria-live="polite">
    <div class="result__heading">
      <div><p class="eyebrow">第 {{ submission.version }} 次提交</p><h3>{{ statusLabel(submission.status) }}</h3></div>
      <span class="status-pill">{{ statusLabel(submission.status) }}</span>
    </div>
    <p v-if="activeStatus && !pollingStopped">系统正在安全隔离环境中编译并运行你的程序。</p>
    <template v-else-if="activeStatus && pollingStopped">
      <p>判题仍在进行。自动查询已停止，你可以手动刷新结果。</p>
      <button type="button" class="refresh-button" :disabled="isRefreshing" @click="emit('refresh')">{{ isRefreshing ? '正在刷新…' : '刷新判题结果' }}</button>
    </template>
    <dl v-else>
      <div><dt>通过用例</dt><dd>{{ submission.passed_case_count ?? 0 }} / {{ submission.executed_case_count ?? 0 }}</dd></div>
      <div><dt>耗时</dt><dd>{{ submission.time_ms ?? '—' }}{{ submission.time_ms != null ? ' ms' : '' }}</dd></div>
      <div><dt>内存</dt><dd>{{ submission.memory_kb ?? '—' }}{{ submission.memory_kb != null ? ' KiB' : '' }}</dd></div>
    </dl>
    <pre v-if="submission.status === 'CE' && submission.compiler_output" class="compiler-output">{{ submission.compiler_output }}</pre>
    <p v-if="submission.status === 'SYSTEM_ERROR'">请稍后重新提交；这不是你的代码错误。</p>
  </section>
</template>

<style scoped>
.result { margin-top: 20px; padding: 16px; border: 1px solid #4b7862; border-radius: 9px; background: #0c3326; }.result--AC { border-color: #4ade80; }.result--SYSTEM_ERROR { border-color: #facc15; }.result--WA, .result--RE, .result--TLE, .result--CE { border-color: #f59e8b; }.result__heading { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }.result h3 { margin: 5px 0; }.eyebrow { margin: 0; color: #9fcbb0; font-size: 12px; }.status-pill { padding: 4px 8px; border-radius: 999px; color: #d9fbe4; background: #1d6247; font-size: 12px; white-space: nowrap; }.result p { color: #c5dbcf; line-height: 1.55; }.result dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }.result dt { color: #9fcbb0; font-size: 12px; }.result dd { margin: 4px 0 0; }.compiler-output { max-height: 180px; overflow: auto; padding: 10px; border-radius: 6px; color: #fecaca; background: #09281e; white-space: pre-wrap; }.refresh-button { margin-top: 2px; border: 1px solid #76b78f; border-radius: 7px; padding: 8px 11px; color: #e8f8ed; background: transparent; font-weight: 700; cursor: pointer; }.refresh-button:disabled { cursor: not-allowed; opacity: .65; } @media (max-width: 760px) { .result dl { grid-template-columns: 1fr; } }
</style>
