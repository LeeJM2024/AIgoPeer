<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../api/auth'
import UiIcon from '../components/UiIcon.vue'

const account = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const route = useRoute()
const router = useRouter()

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const user = await login(account.value.trim(), password.value)
    router.push(
      route.query.redirect ||
        (user.role === 'TEACHER' ? '/teacher' : '/student'),
    )
  } catch (err) {
    error.value =
      err.message === 'INVALID_CREDENTIALS'
        ? '账号或密码不正确。'
        : `登录失败：${err.message}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="auth-layout" aria-labelledby="login-title">
    <header class="login-brand"><span class="brand-mark"><UiIcon name="book" /></span><strong>AlgoPeer</strong></header>
    <form class="auth-form" @submit.prevent="submit">
      <div class="login-heading">
        <h1 id="login-title">登录</h1>
        <p class="muted">算法设计与分析 · 课程工作台</p>
      </div>
      <label
        >账号<input v-model="account" autocomplete="username" placeholder="学号或教师账号" autocapitalize="none" spellcheck="false" required
      /></label>
      <label
        >密码<input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
      /></label>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button" :disabled="busy">
        {{ busy ? '正在验证…' : '登录' }}
      </button>
      <p class="form-help">没有账号？<RouterLink to="/register">学生注册</RouterLink></p>
    </form>
    <p class="login-caption">教师与学生使用同一入口登录</p>
  </section>
</template>
