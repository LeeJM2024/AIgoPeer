<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import UiIcon from './UiIcon.vue'

defineProps({ controls: { type: Boolean, default: true } })
const stage = ref(null)
const failed = ref(false)
const playing = ref(true)
const inViewport = ref(true)
const pageVisible = ref(!document.hidden)
const reduced = ref(false)
let observer
let preference
const syncVisibility = () => { pageVisible.value = !document.hidden }
const syncPreference = () => { reduced.value = preference?.matches ?? false }
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
})
onUnmounted(() => {
  observer?.disconnect()
  preference?.removeEventListener('change', syncPreference)
  document.removeEventListener('visibilitychange', syncVisibility)
})
</script>

<template>
  <div ref="stage" class="algorithm-artwork" :class="{ 'is-moving': playing && inViewport && pageVisible && !reduced }">
    <img v-if="!failed" :src="'/artwork/algorithm-foundations.png'" width="1693" height="929" alt="蓝绿色树结构、数组面板与数据方块构成的立体算法插画" fetchpriority="high" decoding="async" @error="failed = true" />
    <svg v-else class="algorithm-drawing" viewBox="0 0 640 440" role="img" aria-label="二叉树与数组的算法结构图">
      <g class="tree-connections" fill="none" stroke="currentColor" stroke-width="4">
        <path d="M344 92 236 180 160 284M236 180 288 284M344 92 452 180 400 284M452 180 528 284" />
      </g>
      <g class="tree-nodes" fill="currentColor">
        <rect x="313" y="61" width="62" height="62" rx="16" />
        <rect x="212" y="156" width="48" height="48" rx="12" />
        <rect x="428" y="156" width="48" height="48" rx="12" />
        <rect x="140" y="264" width="40" height="40" rx="10" />
        <rect x="268" y="264" width="40" height="40" rx="10" />
        <rect x="380" y="264" width="40" height="40" rx="10" />
        <rect x="508" y="264" width="40" height="40" rx="10" />
      </g>
      <g class="array-tiles" fill="currentColor"><rect x="160" y="348" width="56" height="42" rx="5" /><rect x="228" y="348" width="56" height="42" rx="5" /><rect x="296" y="348" width="56" height="42" rx="5" /><rect x="364" y="348" width="56" height="42" rx="5" /></g>
    </svg>
    <button v-if="controls && !reduced" class="artwork-toggle" type="button" :aria-label="playing ? '暂停宣传动画' : '播放宣传动画'" :aria-pressed="!playing" @click="playing = !playing"><UiIcon :name="playing ? 'pause' : 'play'" /></button>
  </div>
</template>

<style scoped>
.algorithm-artwork { position: relative; width: 100%; height: 100%; min-height: 200px; background: var(--surface); overflow: hidden; isolation: isolate; }
.algorithm-artwork > img { display: block; width: 100%; height: 100%; object-fit: cover; }
.algorithm-drawing { display: block; width: 100%; height: 100%; color: var(--primary); background: var(--studio-dark); }
.tree-connections { opacity: .45; }
.tree-nodes rect:nth-child(2n) { color: var(--studio-blue); }
.array-tiles { color: var(--studio-paper); }
.artwork-toggle { position: absolute; bottom: 18px; right: 18px; display: grid; place-items: center; width: 44px; height: 44px; min-height: 44px; padding: 0; border: 0; border-radius: 50%; background: var(--studio-dark); color: var(--studio-mint); z-index: 2; }
.artwork-toggle:hover { background: var(--studio-mint); color: var(--studio-dark); }
.artwork-toggle .ui-icon { width: 17px; height: 17px; }
@media (prefers-reduced-motion: no-preference) {
  .algorithm-artwork > img { animation: artwork-settle 1.2s var(--ease-out) both, artwork-breathe 10s ease-in-out 1.2s infinite alternate; animation-play-state: paused; }
  .algorithm-artwork.is-moving > img { animation-play-state: running; }
  .is-moving .tree-nodes rect { animation: node-visit 3.5s ease-in-out both; }
  .tree-nodes rect:nth-child(2) { animation-delay: .15s; }
  .tree-nodes rect:nth-child(3) { animation-delay: .3s; }
  .tree-nodes rect:nth-child(4) { animation-delay: .45s; }
  .tree-nodes rect:nth-child(5) { animation-delay: .6s; }
  .tree-nodes rect:nth-child(6) { animation-delay: .75s; }
  .tree-nodes rect:nth-child(7) { animation-delay: .9s; }
}
@keyframes artwork-settle { from { opacity: 0; transform: scale(1.055) translateY(12px); } to { opacity: 1; transform: scale(1) translateY(0); } }
@keyframes artwork-breathe { from { transform: scale(1) translateY(0); } to { transform: scale(1.035) translateY(-5px); } }
@keyframes node-visit { 0% { opacity: .25; } 35%,100% { opacity: 1; } }
</style>
