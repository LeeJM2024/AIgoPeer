<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../api/auth'
import UiIcon from '../components/UiIcon.vue'
import AuthExperience from '../components/AuthExperience.vue'
import { loginRedirect } from '../router/loginRedirect'

const account = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const showPassword = ref(false)
const route = useRoute()
const router = useRouter()

async function submit() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    const user = await login(account.value.trim(), password.value)
    await router.push(loginRedirect(router, route.query.redirect, user.role))
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
  <AuthExperience showcase>
    <form class="auth-form" aria-labelledby="login-title" @submit.prevent="submit">
      <div class="login-heading">
        <h1 id="login-title">登录课程空间</h1>
        <p class="muted">继续你的编程练习与课程项目。</p>
      </div>
      <label
        >账号<input v-model="account" autocomplete="username" placeholder="请输入学号或教师账号" autocapitalize="none" spellcheck="false" :disabled="busy" required
      /></label>
      <label
        >密码<span class="password-field"><input
          v-model="password"
          aria-label="密码"
          :type="showPassword ? 'text' : 'password'"
          autocomplete="current-password"
          placeholder="请输入密码"
          :disabled="busy"
          required
      /><button class="password-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword"><UiIcon :name="showPassword ? 'eyeOff' : 'eye'" /></button></span></label>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <button type="submit" class="button" :disabled="busy">
        {{ busy ? '正在验证…' : '登录' }}<UiIcon v-if="!busy" name="arrow" />
      </button>
      <p class="form-help">没有账号？<RouterLink to="/register">学生注册</RouterLink></p>
    </form>
    <p class="login-caption"><UiIcon name="shield" />教师与学生使用同一入口，登录后进入对应空间</p>
  </AuthExperience>
</template>
