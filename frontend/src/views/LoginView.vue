<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../api/auth'

const account = ref('T001')
const password = ref('AlgoPeer2026!')
const error = ref('')
const busy = ref(false)
const route = useRoute()
const router = useRouter()

async function submit() {
  error.value = ''; busy.value = true
  try {
    const user = await login(account.value.trim(), password.value)
    router.push(route.query.redirect || (user.role === 'TEACHER' ? '/teacher' : '/student'))
  } catch (err) { error.value = err.message === 'INVALID_CREDENTIALS' ? '账号或密码不正确。' : `登录失败：${err.message}` }
  finally { busy.value = false }
}
</script>

<template>
  <section class="auth-layout">
    <div class="auth-context">
      <p class="section-label">算法设计与分析</p>
      <h1>把每一次评分，都变成有依据的决定。</h1>
      <p>统一管理作业发布、跨班五人评审、教师评分与成绩发布。原始数据、算法建议和教师决定始终清晰分开。</p>
    </div>
    <form class="auth-form" @submit.prevent="submit">
      <div><h2>登录 AlgoPeer</h2><p class="muted">使用课程账号进入对应工作台。</p></div>
      <label>账号<input v-model="account" autocomplete="username" required /></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button" :disabled="busy">{{ busy ? '正在验证…' : '登录' }}</button>
      <p class="form-help">本地演示教师账号已预填；部署前请更换密码与 JWT 密钥。</p>
    </form>
  </section>
</template>
