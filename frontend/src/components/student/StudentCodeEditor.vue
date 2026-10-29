<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: String, required: true },
  disabled: { type: Boolean, default: false },
  maxLength: { type: Number, default: 65536 }
})

const emit = defineEmits(['update:modelValue'])
const gutter = ref(null)
const lineNumbers = computed(() => Array.from(
  { length: Math.max(1, props.modelValue.split('\n').length) },
  (_, index) => index + 1
))

function syncScroll(event) {
  if (gutter.value) gutter.value.scrollTop = event.target.scrollTop
}
</script>

<template>
  <div class="code-editor">
    <pre ref="gutter" class="code-editor__gutter" aria-hidden="true">{{ lineNumbers.join('\n') }}</pre>
    <textarea
      id="source-code"
      class="code-editor__input"
      :value="modelValue"
      :disabled="disabled"
      :maxlength="maxLength"
      spellcheck="false"
      aria-label="C++17 源代码"
      @input="emit('update:modelValue', $event.target.value)"
      @scroll="syncScroll"
    />
  </div>
</template>

<style scoped>
.code-editor { display: grid; grid-template-columns: auto minmax(0,1fr); min-height: 360px; overflow: hidden; border: 1px solid var(--code-bg); border-radius: 9px; background: var(--code-bg); }
.code-editor:focus-within { outline: 2px solid var(--primary); outline-offset: 3px; }
.code-editor__gutter { min-width: 3.4em; height: 360px; margin: 0; padding: 14px 10px; overflow: hidden; border-right: 1px solid #405263; color: #a5b6c7; background: var(--code-bg); font: 14px/1.6 Consolas, 'Cascadia Code', monospace; text-align: right; user-select: none; }
.code-editor__input { width: 100%; min-height: 360px; padding: 14px; border: 0; outline: 0; resize: vertical; color: var(--code-ink); background: transparent; font: 14px/1.6 Consolas, 'Cascadia Code', monospace; tab-size: 2; box-shadow: none; }
.code-editor__input:focus { box-shadow: none; }
.code-editor__input::placeholder { color: #a5b6c7; }
.code-editor__input:disabled { cursor: not-allowed; opacity: .72; }
</style>
