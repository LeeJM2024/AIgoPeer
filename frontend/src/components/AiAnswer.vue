<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps({ content: { type: String, required: true } })
const copied = ref(-1), copyError = ref('')
let copyIndex = 0

function findClosing(source, start, delimiter) {
  let position = start
  while (position < source.length) {
    const found = source.indexOf(delimiter, position)
    if (found < 0) return -1
    let slashes = 0
    for (let index = found - 1; index >= 0 && source[index] === '\\'; index -= 1) slashes += 1
    if (slashes % 2 === 0) return found
    position = found + delimiter.length
  }
  return -1
}

function mathInline(state, silent) {
  const source = state.src, start = state.pos
  const isParen = source.startsWith('\\(', start)
  if ((!isParen && (source[start] !== '$' || source[start + 1] === '$')) || (isParen && !source.startsWith('\\(', start))) return false
  const contentStart = start + (isParen ? 2 : 1), endDelimiter = isParen ? '\\)' : '$'
  const end = findClosing(source, contentStart, endDelimiter)
  if (end <= contentStart || source.slice(contentStart, end).includes('\n')) return false
  if (!silent) { const token = state.push('math_inline', 'math', 0); token.content = source.slice(contentStart, end) }
  state.pos = end + endDelimiter.length
  return true
}

function mathBlock(state, startLine, endLine, silent) {
  const start = state.bMarks[startLine] + state.tShift[startLine]
  const first = state.src.slice(start, state.eMarks[startLine]).trim()
  const delimiter = first === '$$' ? '$$' : first === '\\[' ? '\\]' : null
  if (!delimiter) return false
  let nextLine = startLine + 1; const lines = []
  while (nextLine < endLine) {
    const lineStart = state.bMarks[nextLine] + state.tShift[nextLine]
    const line = state.src.slice(lineStart, state.eMarks[nextLine]).trim()
    if (line === delimiter) break
    lines.push(state.src.slice(lineStart, state.eMarks[nextLine])); nextLine += 1
  }
  if (nextLine >= endLine || silent) return true
  const token = state.push('math_block', 'math', 0); token.block = true; token.content = lines.join('\n').trim(); state.line = nextLine + 1
  return true
}

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
markdown.inline.ruler.before('escape', 'math_inline', mathInline)
markdown.block.ruler.before('fence', 'math_block', mathBlock, { alt: ['paragraph', 'reference', 'blockquote', 'list'] })
markdown.renderer.rules.math_inline = token => katex.renderToString(String(token.content ?? ''), { throwOnError: false, output: 'htmlAndMathml' })
markdown.renderer.rules.math_block = token => `<div class="ai-math-block">${katex.renderToString(String(token.content ?? ''), { throwOnError: false, displayMode: true, output: 'htmlAndMathml' })}</div>`
markdown.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index], language = token.info.trim().split(/\s+/)[0], label = language || '代码'
  const code = token.content.replace(/\n$/, ''), copyId = copyIndex++
  return `<div class="ai-code"><div class="ai-code-heading"><small>${markdown.utils.escapeHtml(label)}</small><button type="button" data-copy-index="${copyId}" data-copy-code="${markdown.utils.escapeHtml(code)}">复制代码</button></div><pre><code class="language-${markdown.utils.escapeHtml(language)}">${markdown.utils.escapeHtml(code)}</code></pre></div>`
}
const rendered = computed(() => { copyIndex = 0; return markdown.render(props.content) })

async function copy(code, index, button) {
  copyError.value = ''
  try { await navigator.clipboard.writeText(code); copied.value = index; if (button) button.textContent = '已复制' }
  catch { copyError.value = '复制失败，请选中代码后手动复制。' }
}
function handleClick(event) {
  const button = event.target.closest?.('[data-copy-code]')
  if (button) void copy(button.dataset.copyCode || '', button.dataset.copyIndex || '', button)
}
onMounted(() => { copyError.value = '' })
onBeforeUnmount(() => { copyError.value = '' })
</script>
<template>
  <div class="ai-answer" @click="handleClick"><div class="ai-markdown" v-html="rendered" /><p v-if="copyError" role="status">{{ copyError }}</p></div>
</template>
<style scoped>
.ai-answer { line-height: 1.8; font-size: 14px; overflow-wrap: anywhere; }
.ai-markdown :deep(p) { margin: 8px 0; white-space: pre-wrap; }
.ai-markdown :deep(h1), .ai-markdown :deep(h2), .ai-markdown :deep(h3), .ai-markdown :deep(h4), .ai-markdown :deep(h5), .ai-markdown :deep(h6) { margin: 18px 0 8px; line-height: 1.4; }
.ai-markdown :deep(ul), .ai-markdown :deep(ol) { margin: 8px 0; padding-left: 24px; }
.ai-markdown :deep(blockquote) { margin: 12px 0; padding: 4px 14px; border-left: 3px solid var(--primary); color: var(--muted); }
.ai-markdown :deep(table) { width: 100%; margin: 16px 0; border-collapse: separate; border-spacing: 0; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; font-size: 13px; }
.ai-markdown :deep(th), .ai-markdown :deep(td) { padding: 10px 12px; border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
.ai-markdown :deep(th) { background: var(--surface-subtle); font-weight: 700; }
.ai-markdown :deep(tr:last-child td) { border-bottom: 0; }
.ai-markdown :deep(th:last-child), .ai-markdown :deep(td:last-child) { border-right: 0; }
.ai-markdown :deep(.ai-math-block) { margin: 18px 0; padding: 12px; overflow-x: auto; text-align: center; background: var(--surface-subtle); border-radius: 12px; }
.ai-markdown :deep(.katex-display) { margin: 0; overflow-x: auto; overflow-y: hidden; }
.ai-markdown :deep(code:not(pre code)) { font-family: Consolas, monospace; padding: 1px 4px; background: var(--surface-subtle); border-radius: 4px; }
.ai-code { margin: 14px 0; border-radius: 12px; background: var(--code-bg); color: var(--code-ink); overflow: hidden; }
.ai-code-heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #ffffff24; }
.ai-code-heading button { color: inherit; background: transparent; border: 1px solid #ffffff50; border-radius: 6px; padding: 6px 10px; cursor: pointer; }
.ai-code pre { margin: 0; padding: 14px; overflow: auto; line-height: 1.7; }
.ai-code pre code { white-space: pre; font-family: Consolas, 'Cascadia Code', monospace; }
@media (max-width: 680px) { .ai-markdown :deep(table) { display: block; overflow-x: auto; white-space: nowrap; } }
</style>
