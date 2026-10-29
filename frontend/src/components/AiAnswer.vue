<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ content: { type: String, required: true } })
const copied = ref(-1), copyError = ref('')
const blocks = computed(() => {
  const pieces = props.content.split(/```([^\n`]*)\n([\s\S]*?)(?:```|$)/g)
  const result = []
  for (let i = 0; i < pieces.length; i += 3) {
    if (pieces[i]) result.push({ type: 'text', lines: pieces[i].split('\n') })
    if (pieces[i + 2] != null) result.push({ type: 'code', language: pieces[i + 1], code: pieces[i + 2].replace(/\n$/, '') })
  }
  return result
})
const inline = (text) => text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map(part => ({
  type: part.startsWith('`') ? 'code' : part.startsWith('**') ? 'strong' : 'text',
  text: part.startsWith('`') ? part.slice(1, -1) : part.startsWith('**') ? part.slice(2, -2) : part,
}))
const clean = (line) => line.replace(/^\s*(?:#{1,6}\s+|[-*]\s+|>\s?)/, '')
async function copy(code, index) {
  copyError.value = ''
  try { await navigator.clipboard.writeText(code); copied.value = index }
  catch { copyError.value = '复制失败，请选中代码后手动复制。' }
}
</script>
<template>
  <div class="ai-answer">
    <template v-for="(block, index) in blocks" :key="index">
      <div v-if="block.type === 'code'" class="ai-code"><div class="ai-code-heading"><small>{{ block.language || '代码' }}</small><button type="button" @click="copy(block.code, index)">{{ copied === index ? '已复制' : '复制代码' }}</button></div><pre><code>{{ block.code }}</code></pre></div>
      <template v-else><template v-for="(line, lineIndex) in block.lines" :key="lineIndex"><component :is="/^\s*#{1,6}\s/.test(line) ? 'h5' : 'p'" v-if="line.trim()" :class="{ 'ai-list-line': /^\s*[-*]\s/.test(line) }"><template v-for="(token, t) in inline(clean(line))" :key="t"><code v-if="token.type === 'code'">{{ token.text }}</code><strong v-else-if="token.type === 'strong'">{{ token.text }}</strong><template v-else>{{ token.text }}</template></template></component></template></template>
    </template>
    <p v-if="copyError" role="status">{{ copyError }}</p>
  </div>
</template>
<style scoped>
.ai-answer { line-height: 1.8; font-size: 14px; overflow-wrap: anywhere; }
p { margin: 8px 0; white-space: pre-wrap; } h5 { font-size: 15px; margin: 18px 0 8px; }
.ai-list-line { padding-left: 14px; border-left: 2px solid var(--border); }
code { font-family: Consolas, monospace; padding: 1px 4px; background: var(--surface-subtle); border-radius: 4px; }
.ai-code { margin: 14px 0; border-radius: 12px; background: var(--code-bg); color: var(--code-ink); overflow: hidden; }
.ai-code-heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #ffffff24; }
.ai-code-heading button { color: inherit; background: transparent; border: 1px solid #ffffff50; border-radius: 6px; padding: 6px 10px; cursor: pointer; }
pre { margin: 0; padding: 14px; overflow: auto; line-height: 1.7; } pre code { padding: 0; background: transparent; border-radius: 0; white-space: pre; }
</style>
