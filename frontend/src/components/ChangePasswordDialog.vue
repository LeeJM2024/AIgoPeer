<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { changePassword } from '../api/auth'
import UiIcon from './UiIcon.vue'

const emit = defineEmits(['close'])
const dialog = ref(null)
const currentPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
const visible = ref(false)
const busy = ref(false)
const changed = ref(false)
const error = ref('')
const fieldErrors = ref({})

onMounted(() => dialog.value.showModal())
onBeforeUnmount(() => dialog.value?.close())

function clearPasswords() {
  currentPassword.value = ''
  newPassword.value = ''
  confirmation.value = ''
}
function close(event) {
  event?.preventDefault()
  if (busy.value) return
  clearPasswords()
  emit('close')
}
async function submit() {
  if (busy.value) return
  error.value = ''
  const errors = {}
  if (!currentPassword.value) errors.current = '请输入当前密码。'
  const length = Array.from(newPassword.value).length
  if (length < 10 || length > 128 || !newPassword.value.trim())
    errors.new = '新密码须为 10～128 位，不能全为空格。'
  else if (newPassword.value === currentPassword.value)
    errors.new = '新密码不能与当前密码相同。'
  if (newPassword.value !== confirmation.value) errors.confirm = '两次输入的新密码不一致。'
  fieldErrors.value = errors
  if (Object.keys(errors).length) return
  busy.value = true
  try {
    await changePassword(currentPassword.value, newPassword.value, confirmation.value)
    clearPasswords()
    visible.value = false
    changed.value = true
  } catch (err) {
    if (err.code === 'CURRENT_PASSWORD_INCORRECT') fieldErrors.value = { current: err.message }
    else error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="password-dialog" aria-labelledby="password-dialog-title" aria-describedby="password-dialog-description" @cancel="close">
      <div class="password-heading">
        <span class="password-symbol"><UiIcon :name="changed ? 'check' : 'shield'" /></span>
        <h2 id="password-dialog-title">{{ changed ? '密码已修改' : '修改密码' }}</h2>
        <p id="password-dialog-description" class="muted">{{ changed ? '密码已更新，其他设备已退出登录。' : '验证当前密码后，为你的课程账号设置新密码。' }}</p>
      </div>
      <button v-if="changed" class="button password-done" type="button" @click="close">完成</button>
      <form v-else class="password-form" @submit.prevent="submit">
        <label for="account-current-password">当前密码</label>
        <input id="account-current-password" v-model="currentPassword" :type="visible ? 'text' : 'password'" autocomplete="current-password" maxlength="256" autofocus required :disabled="busy" :aria-invalid="Boolean(fieldErrors.current)" :aria-describedby="fieldErrors.current ? 'current-password-error' : undefined" />
        <p v-if="fieldErrors.current" id="current-password-error" class="password-error" role="alert">{{ fieldErrors.current }}</p>
        <label for="account-new-password">新密码</label>
        <input id="account-new-password" v-model="newPassword" :type="visible ? 'text' : 'password'" autocomplete="new-password" minlength="10" maxlength="128" required :disabled="busy" :aria-invalid="Boolean(fieldErrors.new)" :aria-describedby="fieldErrors.new ? 'new-password-error' : 'new-password-hint'" />
        <p id="new-password-hint" class="password-hint">10～128 位，建议组合使用字母、数字和符号。</p>
        <p v-if="fieldErrors.new" id="new-password-error" class="password-error" role="alert">{{ fieldErrors.new }}</p>
        <label for="account-confirm-password">确认新密码</label>
        <input id="account-confirm-password" v-model="confirmation" :type="visible ? 'text' : 'password'" autocomplete="new-password" minlength="10" maxlength="128" required :disabled="busy" :aria-invalid="Boolean(fieldErrors.confirm)" :aria-describedby="fieldErrors.confirm ? 'confirm-password-error' : undefined" />
        <p v-if="fieldErrors.confirm" id="confirm-password-error" class="password-error" role="alert">{{ fieldErrors.confirm }}</p>
        <button class="password-visibility" type="button" :aria-pressed="visible" :disabled="busy" @click="visible = !visible"><UiIcon :name="visible ? 'eyeOff' : 'eye'" />{{ visible ? '隐藏密码' : '显示密码' }}</button>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <div class="password-actions">
          <button class="button button-secondary" type="button" :disabled="busy" @click="close">取消</button>
          <button class="button" type="submit" :disabled="busy">{{ busy ? '正在保存…' : '保存新密码' }}</button>
        </div>
      </form>
    </dialog>
  </Teleport>
</template>

<style scoped>
.password-dialog {
  width: min(440px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  box-sizing: border-box;
  padding: clamp(22px, 5vw, 32px);
  border: 1px solid var(--border);
  border-radius: 28px;
  color: var(--ink);
  background: var(--page-gradient);
  box-shadow: 0 24px 80px rgb(20 36 62 / 20%);
  overflow: auto;
}
.password-dialog::backdrop { background: rgb(20 36 62 / 35%); }
.password-heading { margin-bottom: 24px; }
.password-heading h2 { margin: 14px 0 6px; font-size: 24px; }
.password-heading p { margin: 0; font-size: 14px; }
.password-symbol { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 16px; color: var(--primary); background: var(--primary-soft); }
.password-form { display: grid; gap: 8px; }
.password-form label { margin-top: 8px; font-size: 14px; font-weight: 600; }
.password-form input { box-sizing: border-box; width: 100%; min-height: 46px; }
.password-form input[aria-invalid='true'] { border-color: var(--danger); }
.password-hint, .password-error { margin: 0; font-size: 13px; }
.password-hint { color: var(--muted); }
.password-error { color: var(--danger); }
.password-visibility { display: inline-flex; align-items: center; gap: 8px; justify-self: start; min-height: 44px; padding: 0 4px; border: 0; background: transparent; color: var(--muted); font-size: 14px; }
.password-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 12px; }
.password-done { width: 100%; }
</style>
