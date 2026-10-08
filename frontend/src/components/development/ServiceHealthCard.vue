<script setup>
defineProps({
  isLoading: Boolean,
  error: {
    type: String,
    default: ''
  },
  health: {
    type: Object,
    default: null
  }
})

defineEmits(['refresh'])
</script>

<template>
  <section class="health-card" aria-labelledby="health-title">
    <div>
      <p class="section-kicker">真实后端连接</p>
      <h2 id="health-title">服务状态</h2>
    </div>
    <p v-if="isLoading" role="status">正在检查后端…</p>
    <p v-else-if="error" class="health-card__error" role="alert">连接失败：{{ error }}</p>
    <p v-else-if="health" class="health-card__success">{{ health.service }} · {{ health.status }}</p>
    <button type="button" @click="$emit('refresh')">重新检查</button>
  </section>
</template>

<style scoped>
.health-card { display: grid; gap: 12px; padding: 20px; border: 1px solid #d7e5dc; border-radius: 10px; background: white; }
.section-kicker { margin: 0; color: #276749; font-size: 13px; font-weight: 700; }
h2 { margin: 4px 0 0; font-size: 18px; }
.health-card__success { margin: 0; color: #17603f; font-weight: 600; }
.health-card__error { margin: 0; color: #b42318; }
button { justify-self: start; padding: 8px 12px; border: 1px solid #98b9a5; border-radius: 6px; color: #0d4d3a; background: white; cursor: pointer; }
</style>
