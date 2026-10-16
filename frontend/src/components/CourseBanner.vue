<script setup>
import AlgorithmArtwork from './AlgorithmArtwork.vue'
import UiIcon from './UiIcon.vue'
defineProps({ student: Boolean })
</script>

<template>
  <section class="course-banner" aria-label="算法设计与分析课程">
    <div class="course-banner__copy">
      <h2 v-if="student">把一个想法，<br />写成一种解法</h2>
      <h2 v-else>专注教学，<br />看见每一步进展</h2>
      <p>{{ student ? '从理解原理到动手实现，在每次练习中积累自己的答案。' : '编程练习、课程项目与学习反馈，在这里有序展开。' }}</p>
      <a v-if="student" class="banner-link" href="#assignment-workspace">开始学习<UiIcon name="arrow" /></a>
      <RouterLink v-else class="banner-link" to="/teacher/assignments">进入作业管理<UiIcon name="arrow" /></RouterLink>
    </div>
    <div class="course-banner__art"><AlgorithmArtwork /></div>
  </section>
</template>

<style scoped>
.course-banner { display: grid; grid-template-columns: minmax(0,1fr) 47%; background: var(--studio-dark); color: var(--studio-paper); overflow: hidden; border-radius: 6px; min-height: 262px; }
.course-banner__copy { padding: 32px 0 32px 36px; position: relative; z-index: 1; align-self: center; }
.course-banner h2 { margin: 0; font-size: clamp(28px,2.7vw,39px); line-height: 1.3; letter-spacing: -.04em; font-weight: 650; }
.course-banner p { color: var(--studio-muted); font-size: 14px; max-width: 34ch; margin: 14px 0 20px; }
.banner-link { display: inline-flex; align-items: center; gap: 16px; color: var(--studio-mint); font-size: 14px; font-weight: 650; text-decoration: none; min-height: 44px; }
.banner-link .ui-icon { transition: transform 180ms var(--ease-out); }
.banner-link:hover .ui-icon { transform: translateX(5px); }
.course-banner__art { position: relative; min-width: 0; min-height: 262px; }
.course-banner__art :deep(.algorithm-artwork) { position: absolute; inset: 0; }
@media (max-width: 680px) { .course-banner { grid-template-columns: minmax(0,1fr) 36%; min-height: 230px; } .course-banner__copy { padding: 25px 0 25px 22px; } .course-banner h2 { font-size: 25px; } .course-banner p { font-size: 13px; margin: 12px 0; } .course-banner__art { min-height: 230px; } .course-banner__art :deep(img) { object-position: 62% center; } }
</style>
