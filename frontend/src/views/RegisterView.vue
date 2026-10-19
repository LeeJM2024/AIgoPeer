<script setup>
import { ref } from 'vue'
import { register } from '../api/auth'
import AuthExperience from '../components/AuthExperience.vue'

const studentNo = ref('')
const name = ref('')
const password = ref('')
const confirmation = ref('')
const busy = ref(false)
const error = ref('')
const registered = ref(false)

async function submit() {
  if (busy.value) return
  error.value = ''
  if (password.value !== confirmation.value) {
    error.value = '两次输入的密码不一致。'
    return
  }
  if (!studentNo.value.trim() || !name.value.trim() || !password.value.trim()) {
    error.value = '请完整填写学号、姓名和密码。'
    return
  }
  busy.value = true
  try {
    await register(studentNo.value.trim(), name.value.trim(), password.value)
    registered.value = true
    password.value = ''
    confirmation.value = ''
  } catch (err) {
    error.value = err.code === 'VALIDATION_ERROR'
      ? '请检查学号格式、姓名及密码长度（10～128位）。'
      : err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthExperience>
    <section v-if="registered" class="auth-form">
      <h1 id="register-title">注册成功</h1>
      <p class="notice notice-success" role="status">账号已创建，请使用学号和刚设置的密码登录。</p>
      <p class="muted">请联系任课教师将你加入课程班级，加入后即可查看该班作业。</p>
      <RouterLink class="button" to="/login">前往登录</RouterLink>
    </section>
    <form v-else class="auth-form" @submit.prevent="submit">
      <div class="login-heading">
        <h1 id="register-title">学生注册</h1>
        <p class="muted">创建你的账号，加入班级后即可查看课程作业。</p>
      </div>
      <label>学号<input v-model="studentNo" autocomplete="username" placeholder="请输入本人学号" autocapitalize="none" spellcheck="false" maxlength="32" pattern="[A-Za-z0-9][A-Za-z0-9_.\-]*" title="学号最多32位，可包含字母、数字、点、下划线和短横线" :disabled="busy" required /></label>
      <label>姓名<input v-model="name" autocomplete="name" placeholder="请输入姓名" maxlength="100" :disabled="busy" required /></label>
      <label>密码<input v-model="password" type="password" autocomplete="new-password" placeholder="10～128位" minlength="10" maxlength="128" :disabled="busy" required /></label>
      <label>确认密码<input v-model="confirmation" type="password" autocomplete="new-password" placeholder="请再次输入密码" minlength="10" maxlength="128" :disabled="busy" required /></label>
      <p class="form-help">注册后请联系任课教师加入课程班级。</p>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button" :disabled="busy">{{ busy ? '正在注册…' : '注册账号' }}</button>
      <p class="form-help">已有账号？<RouterLink to="/login">返回登录</RouterLink></p>
    </form>
    <p class="login-caption">教师账号由课程管理员提供</p>
  </AuthExperience>
</template>
