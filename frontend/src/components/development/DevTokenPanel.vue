<script setup>
import { ref } from 'vue'

const emit = defineEmits(['updated'])
const token = ref(localStorage.getItem('algopeer_token') ?? '')
const message = ref('')

function saveToken() {
  const trimmedToken = token.value.trim()
  if (trimmedToken) {
    localStorage.setItem('algopeer_token', trimmedToken)
    message.value = '测试 Token 已保存。'
  } else {
    localStorage.removeItem('algopeer_token')
    message.value = '测试 Token 已清除。'
  }
  emit('updated')
}
</script>

<template>
  <section class="dev-panel" aria-labelledby="dev-token-title">
    <div>
      <p class="section-kicker">开发环境专用</p>
      <h2 id="dev-token-title">测试身份</h2>
      <p>粘贴有效 JWT 后，可前往“我的作业”验证真实权限与接口结果。</p>
    </div>
    <label for="dev-token">Bearer Token</label>
    <textarea id="dev-token" v-model="token" rows="3" spellcheck="false" placeholder="粘贴 JWT，不含 Bearer 前缀" />
    <div class="dev-panel__actions">
      <button type="button" @click="saveToken">保存 Token</button>
      <span v-if="message" role="status">{{ message }}</span>
    </div>
  </section>
</template>

<style scoped>
.dev-panel { display: grid; gap: 12px; padding: 20px; border: 1px solid #b8d5c4; border-radius: 10px; background: #f4fbf6; }
.section-kicker { margin: 0; color: #276749; font-size: 13px; font-weight: 700; }
h2 { margin: 4px 0 6px; font-size: 18px; }
p { margin: 0; color: #475467; }
label { color: #344054; font-size: 14px; font-weight: 600; }
textarea { width: 100%; resize: vertical; padding: 10px; border: 1px solid #98b9a5; border-radius: 6px; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
.dev-panel__actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
button { padding: 8px 12px; border: 0; border-radius: 6px; color: white; background: #0d4d3a; cursor: pointer; }
span { color: #276749; font-size: 14px; }
</style>
