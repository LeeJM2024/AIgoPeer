<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import UiIcon from './UiIcon.vue'
import { buildMergeTimeline } from '../presentation/mergeTimeline'
defineProps({ controls: { type: Boolean, default: true } })
const stage = ref(null),
  playing = ref(true),
  inViewport = ref(true),
  pageVisible = ref(!document.hidden),
  reduced = ref(false),
  mounted = ref(false),
  index = ref(0)
const frames = buildMergeTimeline()
const frame = computed(() => frames[index.value])
const moving = computed(
  () =>
    mounted.value &&
    playing.value &&
    inViewport.value &&
    pageVisible.value &&
    !reduced.value &&
    index.value < frames.length - 1
)
const code = [
  'def merge_sort(a):',
  '  if len(a) < 2: return a',
  '  mid = len(a) // 2',
  '  left = merge_sort(a[:mid])',
  '  right = merge_sort(a[mid:])',
  '  # compare left[i], right[j]',
  '  # append the smaller item',
  '  return merge(left, right)'
]
let observer, preference, timer
function clearTimer() {
  if (timer) clearTimeout(timer)
  timer = null
}
function advance() {
  if (index.value < frames.length - 1) index.value++
  if (index.value === frames.length - 1) playing.value = false
}
function step() {
  playing.value = false
  advance()
}
function replay() {
  clearTimer()
  index.value = 0
  playing.value = !reduced.value
}
function syncVisibility() {
  pageVisible.value = !document.hidden
}
function syncPreference() {
  reduced.value = preference?.matches ?? false
  if (reduced.value) playing.value = false
}
watch([moving, index], () => {
  clearTimer()
  if (moving.value) timer = setTimeout(advance, 1200)
})
onMounted(() => {
  preference = window.matchMedia?.('(prefers-reduced-motion: reduce)')
  syncPreference()
  preference?.addEventListener('change', syncPreference)
  document.addEventListener('visibilitychange', syncVisibility)
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(([entry]) => {
      inViewport.value = entry.isIntersecting
    })
    observer.observe(stage.value)
  }
  mounted.value = true
})
onUnmounted(() => {
  clearTimer()
  observer?.disconnect()
  preference?.removeEventListener('change', syncPreference)
  document.removeEventListener('visibilitychange', syncVisibility)
})
</script>
<template>
  <figure
    ref="stage"
    class="algorithm-artwork"
    :class="{ 'is-moving': moving, 'reduced-motion': reduced }"
  >
    <svg
      class="merge-poster"
      viewBox="0 0 960 450"
      role="img"
      aria-label="归并排序演算：数组 8、3、5、1 经过拆分、比较和合并，得到 1、3、5、8"
    >
      <g class="poster-labels">
        <text x="35" y="30">归并排序</text>
        <text x="925" y="30" text-anchor="end">分而治之</text>
      </g>
      <g
        class="merge-guides"
        fill="none"
        stroke-width="3"
        stroke-linecap="round"
      >
        <path
          d="M265 110v22q0 16-16 16H105q-16 0-16 16v8M410 110v22q0 16 16 16h89q16 0 16 16v8M105 225v22q0 16-16 16H69M150 225v22q0 16 16 16h72M495 225v22q0 16-16 16h-9M540 225v22q0 16 16 16h75M105 225v88q0 19 19 19h105q0 0 0 18M531 225v88q0 19-19 19H409q0 0 0 18"
        />
      </g>
      <g class="source-ghost">
        <rect x="193" y="54" width="280" height="56" rx="14" />
        <text
          v-for="(value, n) in [8, 3, 5, 1]"
          :key="n"
          :x="226 + n * 72"
          y="93"
        >
          {{ value }}
        </text>
      </g>
      <g class="poster-labels">
        <text x="310" y="155" text-anchor="middle">拆分</text>
        <text x="310" y="276" text-anchor="middle">递归排序</text>
        <text x="510" y="389">合并</text>
      </g>
      <g
        v-for="tile in frame.tiles"
        :key="tile.id"
        class="merge-tile"
        :class="{ 'is-active': tile.active, 'is-sorted': tile.sorted }"
        :style="{ transform: `translate(${tile.x}px,${tile.y}px)` }"
        :data-value="tile.value"
      >
        <rect width="64" height="56" rx="12" />
        <text x="32" y="39">{{ tile.value }}</text>
      </g>
      <g class="poster-code">
        <rect x="680" y="76" width="250" height="270" rx="22" />
        <text x="700" y="111" class="code-filename">merge_sort.py</text>
        <g
          v-for="(line, n) in code"
          :key="line"
          :class="{ 'code-active': frame.line === n + 1 }"
        >
          <rect x="692" :y="129 + n * 24" width="226" height="24" rx="5" />
          <text x="700" :y="146 + n * 24">{{ line }}</text>
        </g>
      </g>
      <text class="poster-labels code-note" x="680" y="375">
        递归结构示意 · merge 过程省略
      </text>
    </svg>
    <figcaption class="algorithm-caption">
      <div>
        <strong>{{ frame.label }}</strong
        ><span>从一个想法，到一段可运行的代码</span>
      </div>
      <div
        v-if="controls"
        class="algorithm-controls"
        role="group"
        aria-label="算法演算控制"
      >
        <button
          v-if="!reduced"
          type="button"
          :aria-label="playing ? '暂停演算' : '播放演算'"
          :aria-pressed="!playing"
          :disabled="index === frames.length - 1"
          @click="playing = !playing"
        >
          <UiIcon :name="playing ? 'pause' : 'play'" /></button
        ><button
          type="button"
          aria-label="下一步演算"
          :disabled="index === frames.length - 1"
          @click="step"
        >
          <UiIcon name="arrow" /></button
        ><button type="button" aria-label="重新演算" @click="replay">
          <UiIcon name="replay" />
        </button>
      </div>
    </figcaption>
  </figure>
</template>
<style scoped>
.algorithm-artwork {
  margin: 0;
  width: 100%;
  overflow: hidden;
  background: var(--art-gradient);
  border-radius: 38px 120px 38px 38px;
  padding: 16px 12px 0;
  color: var(--ink);
}
.merge-poster {
  display: block;
  width: 100%;
  height: auto;
  max-height: 440px;
  overflow: visible;
}
.poster-labels {
  fill: var(--muted);
  font: 16px var(--font-ui);
}
.merge-guides {
  stroke: var(--art-line);
}
.source-ghost rect {
  fill: var(--surface);
  opacity: 0.6;
}
.source-ghost text {
  fill: var(--muted);
  opacity: 0.5;
  font: 600 29px var(--font-ui);
  text-anchor: middle;
}
.merge-tile {
  transition:
    transform 650ms var(--ease-travel),
    opacity 200ms ease;
}
.merge-tile rect {
  fill: var(--surface);
}
.merge-tile text {
  fill: var(--ink);
  font: 650 32px var(--font-ui);
  text-anchor: middle;
}
.merge-tile.is-sorted rect {
  fill: var(--ink);
}
.merge-tile.is-active rect {
  fill: var(--primary);
}
.merge-tile.is-sorted text,
.merge-tile.is-active text {
  fill: white;
}
.poster-code > rect {
  fill: var(--code-bg);
}
.poster-code text {
  font:
    11.5px Consolas,
    monospace;
  fill: var(--code-ink);
  white-space: pre;
}
.poster-code .code-filename {
  font: 15px var(--font-ui);
  fill: white;
}
.poster-code g rect {
  fill: transparent;
}
.poster-code .code-active rect {
  fill: #344f78;
}
.poster-code .code-active text {
  fill: white;
}
.code-note {
  font-size: 14px;
}
.algorithm-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 8px 22px 22px;
  min-height: 76px;
}
.algorithm-caption > div:first-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.algorithm-caption strong {
  font-size: 14px;
  font-weight: 550;
  overflow-wrap: anywhere;
}
.algorithm-caption span {
  font-size: 12px;
  color: var(--muted);
}
.algorithm-controls {
  display: flex;
  gap: 6px;
  flex: none;
}
.algorithm-controls button {
  display: grid;
  place-items: center;
  width: 44px;
  min-height: 44px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink);
}
.algorithm-controls button:hover {
  background: var(--primary-soft);
  color: var(--primary);
}
.algorithm-controls .ui-icon {
  width: 17px;
  height: 17px;
}
.reduced-motion .merge-tile {
  transition: none;
}
.algorithm-caption span {
  font-size: 13px;
}
@media (min-width: 761px) and (max-width: 900px) {
  .poster-code,
  .code-note {
    display: none;
  }
  .merge-poster {
    width: 145%;
    max-width: none;
    transform: translateX(-2%);
  }
  .algorithm-caption {
    flex-wrap: wrap;
  }
  .algorithm-caption > div:first-child {
    flex: 1 1 100%;
  }
  .algorithm-controls {
    margin-left: auto;
  }
}
@media (max-width: 760px) {
  .algorithm-artwork {
    border-radius: 26px 64px 26px 26px;
    padding: 14px 0 0;
  }
  .poster-code,
  .code-note {
    display: none;
  }
  .merge-poster {
    width: 145%;
    max-width: none;
    transform: translateX(-2%);
  }
  .algorithm-caption {
    padding: 10px 18px 20px;
    flex-wrap: wrap;
  }
  .algorithm-caption > div:first-child {
    flex: 1 1 100%;
  }
  .algorithm-caption strong {
    font-size: 13px;
  }
  .algorithm-controls {
    margin-left: auto;
  }
}
@media (prefers-reduced-motion: reduce) {
  .merge-tile {
    transition: none;
  }
}
</style>
