<script setup>
import { computed, ref } from 'vue'
import AlgorithmArtwork from './AlgorithmArtwork.vue'
import UiIcon from './UiIcon.vue'

defineProps({ showcase: Boolean })
const active = ref(0)
const previews = [
  { name: '课程总览', title: '教学安排，一目了然', detail: '查看真实课程状态，从作业和待办直接进入下一步。', file: '/artwork/preview-teacher.jpg' },
  { name: '编程练习', title: '把思路写进代码', detail: '阅读题目、提交 C++17 代码，再从判题结果中验证解法。', file: '/artwork/preview-code.jpg' },
  { name: '学习空间', title: '每份作业，各有进展', detail: '集中查看课程作业、材料检查状态和已发布的成绩反馈。', file: '/artwork/preview-student.jpg' },
]
const current = computed(() => previews[active.value])
</script>

<template>
  <div class="auth-experience">
    <header class="auth-topbar">
      <RouterLink class="login-brand" to="/login"><span class="brand-mark"><UiIcon name="code" /></span><span><strong>AlgoPeer</strong><small>算法设计与分析</small></span></RouterLink>
      <nav aria-label="公开页面导航"><a v-if="showcase" href="#platform-tour">工作台预览<UiIcon name="arrow" /></a><RouterLink v-else to="/login">返回登录<UiIcon name="arrow" /></RouterLink></nav>
    </header>
    <div class="auth-stage">
      <div class="auth-folder">
        <div class="auth-folder__body"><slot /></div>
        <div class="folder-tabs" aria-label="课程内容"><span>算法原理</span><span>代码实践</span><span>课程项目</span></div>
      </div>
      <section class="auth-studio" aria-labelledby="studio-title">
        <div class="auth-studio__copy"><h2 id="studio-title">算法有逻辑，<br />学习有迹可循</h2><p>从一个想法，到一段可运行的代码。</p></div>
        <div class="auth-studio__art"><AlgorithmArtwork /></div>
        <div class="auth-studio__foot"><span>理解原理，动手实现</span><UiIcon name="code" /></div>
      </section>
    </div>
    <section v-if="showcase" id="platform-tour" class="platform-tour" aria-labelledby="tour-title">
      <div class="tour-intro"><h2 id="tour-title">为算法课堂而设计</h2><p>把教学安排、代码实践和学习反馈放在同一条清晰的路径上。</p></div>
      <div class="tour-stage">
        <div class="tour-picture"><Transition name="preview" mode="out-in"><img :key="current.file" :src="current.file" width="1440" height="900" :alt="`${current.name}的本地演示界面截图`" loading="lazy" decoding="async" /></Transition></div>
        <div class="tour-copy"><Transition name="preview" mode="out-in"><div :key="active"><h3>{{ current.title }}</h3><p>{{ current.detail }}</p></div></Transition><div class="tour-controls" role="group" aria-label="选择工作台预览"><button v-for="(item, index) in previews" :key="item.name" type="button" :aria-pressed="active === index" @click="active = index">{{ item.name }}<UiIcon name="arrow" /></button></div><p class="tour-disclaimer">截图来自本地演示数据，仅用于展示界面。</p></div>
      </div>
      <div class="tour-contact-sheet" aria-label="界面缩略预览"><button v-for="(item, index) in previews" :key="item.name" type="button" :aria-label="`预览${item.name}`" :aria-pressed="active === index" @click="active = index"><img :src="item.file" width="1440" height="900" alt="" loading="lazy" decoding="async" /><span>{{ item.name }}<UiIcon name="arrow" /></span></button></div>
    </section>
    <footer class="auth-footer"><strong>AlgoPeer</strong><p>算法设计与分析课程工作台<br /><small>算法插画：<a href="https://github.com/aabhinavg1/compilersutra/blob/main/static/img/dsa/foundations/dsa-foundations-hero-v2.png" target="_blank" rel="noopener noreferrer">CompilerSutra</a> · <a href="/artwork/CompilerSutra-LICENSE.txt" target="_blank" rel="noopener noreferrer">MIT 许可</a></small></p><a v-if="showcase" href="#main-content">返回登录<UiIcon name="arrow" /></a><RouterLink v-else to="/login">返回登录<UiIcon name="arrow" /></RouterLink></footer>
  </div>
</template>

<style scoped>
.auth-experience { width: 100%; max-width: 1600px; margin-inline: auto; }
.auth-topbar { display: flex; justify-content: space-between; align-items: center; padding: 26px 32px 30px; gap: 24px; }
.login-brand { color: var(--ink); text-decoration: none; align-self: auto; }
.login-brand > span:last-child { display: grid; }
.login-brand strong { font-size: 27px; }
.login-brand small { font-size: 13px; }
.auth-topbar nav a { display: inline-flex; align-items: center; gap: 14px; min-height: 44px; color: var(--ink); font-size: 14px; text-decoration: none; }
.auth-topbar nav a:hover { color: var(--primary); }
.auth-stage { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1.05fr); gap: 12px; }
.auth-folder { display: flex; flex-direction: column; min-width: 0; background: var(--surface); border-radius: 6px; overflow: hidden; }
.folder-tabs { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); min-height: 49px; background: var(--studio-mint); color: var(--studio-dark); font-size: 14px; text-align: center; }
.folder-tabs span { display: grid; place-items: center; padding: 12px 5px; }
.folder-tabs span:nth-child(2) { background: var(--studio-blue); }
.folder-tabs span:nth-child(3) { background: var(--studio-apricot); }
.auth-folder__body { width: 100%; max-width: 490px; padding: 44px 36px 36px; margin: auto; }
.auth-studio { display: flex; flex-direction: column; background: var(--studio-dark); color: var(--studio-paper); min-width: 0; min-height: 680px; overflow: hidden; border-radius: 6px; }
.auth-studio__copy { padding: 42px 40px 24px; position: relative; z-index: 1; }
.auth-studio h2 { font-size: clamp(32px,4.7vw,68px); font-weight: 600; line-height: 1.2; letter-spacing: -.05em; margin: 0; }
.auth-studio__copy p { font-size: 16px; color: var(--studio-muted); margin: 18px 0 0; }
.auth-studio__art { position: relative; flex: 1; min-height: 300px; }
.auth-studio__art :deep(.algorithm-artwork) { position: absolute; inset: 0; }
.auth-studio__foot { display: flex; justify-content: space-between; align-items: center; padding: 20px 40px; color: var(--studio-muted); font-size: 14px; }
.platform-tour { padding: 130px 32px 100px; scroll-margin-top: 24px; }
.tour-intro { display: flex; justify-content: space-between; align-items: end; gap: 40px; margin-bottom: 64px; }
.tour-intro h2 { font-size: clamp(30px,3.3vw,48px); margin: 0; line-height: 1.3; font-weight: 600; letter-spacing: -.04em; }
.tour-intro > p { font-size: 16px; max-width: 29ch; margin: 0; }
.tour-stage { display: grid; grid-template-columns: minmax(0,1.35fr) minmax(0,1fr); gap: 60px; align-items: center; }
.tour-picture { aspect-ratio: 1; overflow: hidden; background: var(--studio-blue); display: grid; place-items: center; padding: 24px; }
.tour-picture img { width: 100%; height: auto; display: block; }
.tour-copy { min-width: 0; }
.tour-copy h3 { font-size: clamp(24px,2.4vw,34px); line-height: 1.35; margin-bottom: 18px; font-weight: 600; letter-spacing: -.03em; }
.tour-copy p { font-size: 16px; line-height: 1.8; max-width: 31ch; }
.tour-controls { display: grid; gap: 10px; margin-top: 36px; }
.tour-controls button { display: flex; justify-content: space-between; align-items: center; gap: 12px; text-align: left; padding: 12px 16px; min-height: 48px; border: 0; border-radius: 0; background: var(--surface); color: var(--ink); font-size: 16px; }
.tour-controls button[aria-pressed=true] { background: var(--studio-dark); color: var(--studio-paper); }
.tour-copy .tour-disclaimer { font-size: 13px; color: var(--muted); margin-top: 24px; }
.tour-contact-sheet { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 20px; margin-top: 48px; }
.tour-contact-sheet button { padding: 0; background: transparent; color: var(--ink); border: 0; border-radius: 0; text-align: left; }
.tour-contact-sheet img { width: 100%; height: auto; display: block; }
.tour-contact-sheet span { display: flex; justify-content: space-between; align-items: center; min-height: 48px; font-size: 14px; }
.tour-contact-sheet button[aria-pressed=true] span { color: var(--primary); }
.auth-footer { display: grid; grid-template-columns: 1fr auto; align-items: end; padding: 56px 32px; background: var(--studio-dark); color: var(--studio-paper); }
.auth-footer > strong { grid-column: 1/-1; font-size: clamp(60px,13.5vw,180px); letter-spacing: -.075em; line-height: 1; font-weight: 650; margin: 0 0 34px; }
.auth-footer p { margin: 0; font-size: 14px; color: var(--studio-muted); }
.auth-footer p small { display: inline-block; margin-top: 12px; font-size: 13px; }
.auth-footer p a { color: inherit; }
.auth-footer > a { display: inline-flex; align-items: center; gap: 12px; color: var(--studio-mint); text-decoration: none; min-height: 44px; font-size: 14px; }
.preview-enter-active { transition: opacity 300ms ease, transform 450ms var(--ease-out); }
.preview-leave-active { transition: opacity 140ms ease; }
.preview-enter-from { opacity: 0; transform: translateY(10px); }
.preview-leave-to { opacity: 0; }
@media (prefers-reduced-motion: no-preference) {
  .auth-topbar, .folder-tabs span, .auth-studio__copy h2, .auth-studio__copy p, .auth-studio__foot { animation: studio-arrive 850ms var(--ease-out) both; }
  .folder-tabs span:nth-child(2) { animation-delay: 60ms; }
  .folder-tabs span:nth-child(3) { animation-delay: 120ms; }
  .auth-studio__copy h2 { animation-delay: 100ms; }
  .auth-studio__copy p { animation-delay: 190ms; }
  .auth-studio__foot { animation-delay: 320ms; }
  .auth-folder__body :deep(.auth-form > *) { animation: studio-arrive 700ms var(--ease-out) both; }
  .auth-folder__body :deep(.auth-form > :nth-child(2)) { animation-delay: 100ms; }
  .auth-folder__body :deep(.auth-form > :nth-child(3)) { animation-delay: 170ms; }
  .auth-folder__body :deep(.auth-form > :nth-child(4)) { animation-delay: 240ms; }
  .auth-folder__body :deep(.auth-form > :nth-child(5)) { animation-delay: 310ms; }
}
@media (max-width: 900px) { .auth-folder__body { padding: 32px 24px; } .auth-studio__copy { padding: 32px 24px 24px; } .auth-studio__foot { padding: 20px 24px; } .tour-stage { gap: 28px; } .platform-tour { padding-inline: 20px; } }
@media (max-width: 680px) {
  .auth-topbar { padding: 18px 10px 24px; gap: 14px; }
  .login-brand { gap: 9px; } .login-brand strong { font-size: 22px; } .login-brand small { font-size: 13px; }
  .auth-topbar nav a { font-size: 13px; gap: 5px; } .auth-topbar nav .ui-icon { width: 16px; }
  .auth-stage { grid-template-columns: minmax(0,1fr); gap: 0; }
  .auth-studio { order: -1; min-height: 185px; height: 185px; display: grid; grid-template-columns: 58% minmax(0,1fr); border-radius: 6px 6px 0 0; }
  .auth-studio__copy { padding: 24px 0 20px 20px; align-self: center; } .auth-studio h2 { font-size: 26px; }
  .auth-studio__copy p { font-size: 13px; margin-top: 12px; max-width: 15ch; }
  .auth-studio__art { min-height: 185px; } .auth-studio__art :deep(.algorithm-artwork) { min-height: 185px; } .auth-studio__art :deep(img) { object-position: 65% center; }
  .auth-studio__foot { display: none; }
  .auth-folder { border-radius: 0 0 6px 6px; } .folder-tabs { min-height: 40px; font-size: 13px; } .folder-tabs span { padding: 9px 4px; }
  .auth-folder__body { padding: 27px 24px 28px; }
  .platform-tour { padding: 76px 10px 64px; }
  .tour-intro { display: block; margin-bottom: 32px; } .tour-intro h2 { font-size: 29px; } .tour-intro > p { margin-top: 18px; max-width: none; }
  .tour-stage { grid-template-columns: minmax(0,1fr); gap: 30px; }
  .tour-picture { aspect-ratio: 1.2; padding: 14px; } .tour-copy h3 { font-size: 26px; } .tour-copy p { max-width: none; }
  .tour-controls { margin-top: 20px; } .tour-contact-sheet { grid-template-columns: minmax(0,1fr); gap: 22px; }
  .auth-footer { padding: 36px 20px; grid-template-columns: minmax(0,1fr); } .auth-footer strong { font-size: 19vw; margin-bottom: 24px; } .auth-footer p { font-size: 13px; }
}
</style>
