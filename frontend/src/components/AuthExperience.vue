<script setup>
import AlgorithmArtwork from './AlgorithmArtwork.vue'
import BrandLogo from './BrandLogo.vue'
defineProps({ showcase: Boolean })
</script>
<template>
  <div class="auth-experience" :class="{ 'auth-register': !showcase }">
    <header class="auth-topbar">
      <RouterLink class="auth-brand" to="/login" aria-label="网络空间安全学院 课程登录"
        ><BrandLogo /></RouterLink
      ><span>算法设计与分析</span>
    </header>
    <div class="auth-stage">
      <section
        class="auth-form-column"
        :aria-label="showcase ? '课程登录' : '学生注册'"
      >
        <slot />
      </section>
      <section class="auth-poster" aria-labelledby="poster-title">
        <div class="poster-heading">
          <h2 id="poster-title"><span>写出解法</span><span>讲清思路</span></h2>
          <p>算法设计与分析课程的编程作业、<br />微课项目与学习反馈。</p>
        </div>
        <AlgorithmArtwork />
      </section>
    </div>
    <footer class="auth-footer">
      <span>网络空间安全学院 · 算法设计与分析课程空间</span
      ><RouterLink v-if="!showcase" to="/login"
        >已有账号？返回登录 ↗</RouterLink
      ><span v-else>理解原理，动手实现</span>
    </footer>
  </div>
</template>
<style scoped>
.auth-experience {
  max-width: 1680px;
  margin: auto;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}
.auth-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 32px 40px;
  color: var(--muted);
  font-size: 15px;
}
.auth-brand {
  min-width: 0;
  color: var(--ink);
  text-decoration: none;
}
.auth-topbar > span {
  flex-shrink: 0;
}
.auth-stage {
  flex: 1;
  display: grid;
  grid-template-columns: 34% 66%;
  padding: 8px 32px 30px;
}
.auth-form-column {
  padding: 88px 70px 20px 8px;
  min-width: 0;
  align-self: start;
}
.auth-poster {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 26px;
  padding: 0 0 0 4px;
}
.poster-heading {
  padding: 0 18px;
  container-type: inline-size;
}
.poster-heading h2 {
  margin: 0;
  font-size: clamp(72px, 7vw, 112px);
  line-height: 1.09;
  letter-spacing: -0.05em;
  font-weight: 780;
  color: var(--ink);
}
.poster-heading h2 span {
  display: block;
}
.poster-heading p {
  font-size: 17px;
  line-height: 1.7;
  margin: 20px 0 0;
}
.auth-poster > .algorithm-artwork {
  margin-top: auto;
}
.auth-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  font-size: 12px;
  color: var(--muted);
  padding: 18px 40px 26px;
}
.auth-footer a {
  min-height: 44px;
  display: flex;
  align-items: center;
  text-decoration: none;
}
.auth-footer {
  font-size: 13px;
}
.auth-register .auth-form-column {
  padding-top: 20px;
}
.auth-register .auth-poster {
  justify-content: center;
}
.auth-register .auth-poster > .algorithm-artwork {
  margin-top: 0;
}
@media (prefers-reduced-motion: no-preference) {
  .poster-heading h2 span {
    animation: poster-arrive 800ms var(--ease-out) both;
  }
  .poster-heading h2 span:nth-child(2) {
    animation-delay: 100ms;
  }
  .poster-heading p {
    animation: poster-arrive 700ms var(--ease-out) 190ms both;
  }
  .auth-form-column {
    animation: poster-arrive 650ms var(--ease-out) both;
  }
}
@keyframes poster-arrive {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (min-width: 1650px) {
  .auth-stage {
    padding-inline: 48px;
  }
  .auth-topbar,
  .auth-footer {
    padding-inline: 56px;
  }
  .auth-form-column {
    padding-top: 100px;
  }
}
@media (max-width: 1100px) and (min-width: 761px) {
  .auth-topbar {
    padding: 28px;
  }
  .auth-stage {
    grid-template-columns: 36% 64%;
    padding-inline: 24px;
  }
  .auth-form-column {
    padding: 70px 28px 20px 4px;
  }
  .poster-heading {
    padding-left: 8px;
  }
  .poster-heading h2 {
    font-size: 72px;
  }
  .poster-heading p {
    font-size: 15px;
  }
  .auth-poster > .algorithm-artwork {
    margin-top: 0;
  }
}
@media (max-width: 760px) {
  .auth-topbar {
    padding: 24px 20px;
    font-size: 13px;
  }
  .auth-stage {
    display: flex;
    flex-direction: column;
    padding: 8px 18px 20px;
    gap: 24px;
  }
  .auth-form-column {
    order: 1;
    padding: 26px 22px 28px;
    width: 100%;
    background: var(--surface-translucent);
    border-radius: 28px;
  }
  .auth-poster {
    display: contents;
  }
  .poster-heading {
    order: 0;
    padding: 0 2px;
  }
  .poster-heading h2 {
    font-size: clamp(48px, 15vw, 64px);
  }
  .poster-heading p {
    font-size: 15px;
    margin-top: 20px;
  }
  .auth-poster > .algorithm-artwork {
    order: 2;
    margin: 0;
  }
  .auth-footer {
    padding: 0 20px 24px;
    flex-wrap: wrap;
    font-size: 13px;
  }
  .auth-register .auth-form-column {
    padding-top: 26px;
  }
}
/* Keep the portrait poster stacked; landscape uses the available poster width. */
@media (orientation: landscape) {
  .poster-heading h2 {
    display: flex;
    gap: 0.28em;
    font-size: clamp(24px, 11cqi, 112px);
    white-space: nowrap;
  }
  .poster-heading h2 span {
    flex-shrink: 0;
  }
  .poster-heading p {
    font-size: clamp(12px, 3.1cqi, 17px);
    white-space: nowrap;
  }
  .poster-heading p br {
    display: none;
  }
}
</style>
