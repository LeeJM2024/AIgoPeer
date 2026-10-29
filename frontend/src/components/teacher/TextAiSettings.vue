<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { deleteTextAiSettings, getTextAiSettings, saveTextAiSettings, testTextAiSettings } from '../../api/ai'

const form = reactive({ base_url: 'https://api.deepseek.com', model: 'deepseek-flash', api_key: '', enabled: true, student_daily_limit: 30, allow_full_solution: false })
const saved = ref(null), loading = ref(true), busy = ref(''), error = ref(''), message = ref('')
const hasKey = computed(() => saved.value?.configured && saved.value.base_url === form.base_url.trim().replace(/\/+$/, ''))
const canSubmit = computed(() => form.base_url.trim() && form.model.trim() && (form.api_key.trim() || hasKey.value))
function apply(data) { saved.value = data; Object.assign(form, { ...data, enabled: data.configured ? data.enabled : true, api_key: '' }) }
async function load() {
  loading.value = true; error.value = ''
  try { apply(await getTextAiSettings()) } catch (err) { error.value = err.message } finally { loading.value = false }
}
onMounted(load)
async function action(kind) {
  if (busy.value) return
  busy.value = kind; error.value = ''; message.value = ''
  try {
    const payload = { base_url: form.base_url, model: form.model, api_key: form.api_key.trim() || null,
      enabled: form.enabled, student_daily_limit: form.student_daily_limit, allow_full_solution: form.allow_full_solution }
    if (kind === 'save') { apply(await saveTextAiSettings(payload)); message.value = '课程文字助教配置已保存。' }
    else if (kind === 'test') { const result = await testTextAiSettings(payload); message.value = result.message }
    else { await deleteTextAiSettings(); await load(); message.value = '已删除文字模型密钥，对话记录保留。' }
  } catch (err) { error.value = err.message } finally { busy.value = '' }
}
</script>
<template>
  <div class="text-ai-layout">
    <form class="data-section text-ai-settings" @submit.prevent="action('save')">
      <div class="section-heading"><h2>课程文字助教</h2><span class="badge">{{ saved?.configured ? (saved.enabled ? '已开启' : '已暂停') : '待配置' }}</span></div>
      <p class="muted">老师统一配置，学生无需填写密钥。支持 DeepSeek 和兼容 Chat Completions 的文字服务。</p>
      <p v-if="error" role="alert" class="notice notice-error">{{ error }}</p><p v-if="message" role="status" class="notice notice-success">{{ message }}</p>
      <p v-if="loading" role="status">正在加载配置…</p>
      <button v-else-if="!saved" type="button" class="button button-secondary" @click="load">重新加载</button>
      <fieldset v-else :disabled="!!busy">
        <label for="text-ai-base">接口地址 Base URL</label><input id="text-ai-base" v-model="form.base_url" type="url" required autocomplete="off" spellcheck="false" />
        <small class="muted">填写 HTTPS 地址，例如 https://api.deepseek.com；系统自动追加 /chat/completions。</small>
        <label for="text-ai-model">模型名称</label><input id="text-ai-model" v-model="form.model" required maxlength="128" autocomplete="off" spellcheck="false" />
        <label for="text-ai-key">API Key</label><input id="text-ai-key" v-model="form.api_key" type="password" :required="!hasKey" maxlength="4096" autocomplete="new-password" :placeholder="hasKey ? '已保存密钥，留空继续使用' : '粘贴老师的 API Key'" />
        <small class="muted">密钥加密保存在服务器，不向学生返回；模型调用费用由此账户承担。</small>
        <label for="text-ai-limit">每位学生每日提问次数</label><input id="text-ai-limit" v-model.number="form.student_daily_limit" type="number" min="1" max="200" required />
        <label class="check"><input v-model="form.enabled" type="checkbox" />开启课程文字助教</label>
        <label class="check"><input v-model="form.allow_full_solution" type="checkbox" />允许编程助教提供完整题解</label>
        <small class="muted">默认采用提示辅导：解释已有代码、定位错误、引导下一步。开启完整题解后可进一步提供完整实现。</small>
        <div class="toolbar"><button class="button" type="submit" :disabled="!canSubmit">{{ busy === 'save' ? '正在保存…' : '保存配置' }}</button><button class="button button-secondary" type="button" :disabled="!canSubmit" @click="action('test')">{{ busy === 'test' ? '正在测试…' : '测试文字连接' }}</button></div>
        <small class="muted">连接测试发送一条短消息，测试后点击保存使配置生效。</small>
      </fieldset>
      <button v-if="saved?.configured" class="button button-small button-secondary remove-key" type="button" :disabled="!!busy" @click="action('delete')">删除文字模型密钥</button>
    </form>
    <aside class="text-ai-guide"><p class="eyebrow">ONE COURSE · THREE ASSISTANTS</p><h2>让问题得到下一步</h2><ol><li><strong>编程助教</strong><p>在编程题的编辑器旁解释代码、分析判题错误、讨论复杂度，选中代码后可针对片段提问。</p></li><li><strong>知识点学习</strong><p>学生从课程知识点目录出发，连续追问、看例子、比较算法并练习。</p></li><li><strong>教学建议</strong><p>在学习分析页选择班级，依据真实提交与知识点统计生成课堂安排。</p></li></ol><RouterLink class="button button-secondary" to="/teacher/learning-analysis">前往学习分析</RouterLink><p class="muted">视频评阅使用独立的音视频模型连接，可在上方切换配置。</p></aside>
  </div>
</template>
<style scoped>
.text-ai-layout { display: grid; grid-template-columns: minmax(0,1.2fr) minmax(260px,.8fr); gap: 32px; align-items: start; }
.text-ai-settings { padding: 28px; background: var(--surface,white); border-radius: 24px; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; display: grid; gap: 10px; } label { font-weight: 600; margin-top: 14px; }
input:not([type=checkbox]) { width: 100%; box-sizing: border-box; min-height: 44px; border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; background: var(--surface,white); color: var(--ink); }
small,p { line-height: 1.7; } .check { display: flex; gap: 10px; align-items: center; } .check input { width: 18px; height: 18px; } .remove-key { margin-top: 24px; }
.text-ai-guide { padding: 24px 10px; } .text-ai-guide h2 { font-size: 28px; } .text-ai-guide ol { padding-left: 22px; } .text-ai-guide li { margin: 26px 0; padding-left: 6px; }
@media(max-width:850px) { .text-ai-layout { grid-template-columns: 1fr; } .text-ai-settings { padding: 20px; } }
</style>
