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
.result { margin-top: 22px; padding: 18px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-subtle); color: var(--ink); }
.result--AC { border-color: #a4ceb6; background: var(--success-soft); }
.result--SYSTEM_ERROR { border-color: #ddc48f; background: var(--warning-soft); }
.result--WA, .result--RE, .result--TLE, .result--CE { border-color: #ecc8c3; background: var(--danger-soft); }
.result__heading { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.result h3 { margin: 5px 0; }
.eyebrow { margin: 0; color: var(--muted); font-size: 11px; }
.result--AC .status-pill { color: var(--success); background: white; }
.result--WA .status-pill, .result--RE .status-pill, .result--TLE .status-pill, .result--CE .status-pill { color: var(--danger); background: white; }
.result p { color: var(--muted); line-height: 1.7; font-size: 13px; }
.result dl { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; margin-bottom: 0; }
.result dt { color: var(--muted); font-size: 11px; }
.result dd { margin: 5px 0 0; font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.compiler-output { max-height: 220px; overflow: auto; padding: 14px; border-radius: 7px; color: var(--danger); background: var(--surface); white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.7 Consolas, monospace; }
.refresh-button { min-height: 40px; padding: 8px 12px; border: 1px solid var(--input-border); border-radius: 7px; color: var(--primary); background: var(--surface); font-weight: 600; }
@media (max-width: 600px) { .result dl { grid-template-columns: minmax(0,1fr); } }
</style>
