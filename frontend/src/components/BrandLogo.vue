<script setup>
import schoolLogo from '../assets/hust-cse-logo.png'
</script>

<template>
  <span class="brand-logo">
    <img
      :src="schoolLogo"
      alt="华中科技大学 网络空间安全学院"
      width="302"
      height="71"
    />
  </span>
</template>
<style scoped>
.brand-logo {
  display: inline-flex;
  align-items: center;
  line-height: 1;
  width: 240px;
  max-width: 100%;
}
.brand-logo img {
  display: block;
  width: 100%;
  height: auto;
  /* Recolor the supplied artwork without redrawing its lettering or alpha. */
  filter: brightness(0);
}
@media (max-width: 760px) {
  .brand-logo {
    width: min(44.5vw, 192px);
  }
}
</style>
