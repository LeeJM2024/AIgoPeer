<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { deleteAiVideoSettings, getAiVideoSettings, saveAiVideoSettings, testAiVideoSettings } from '../../api/teacher'
import UiIcon from '../../components/UiIcon.vue'

defineProps({ embedded: { type: Boolean, default: false } })

const presets = {
  qwen: { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen3.5-omni-flash',
    docs: 'https://help.aliyun.com/zh/model-studio/qwen-omni' },
  gemini: { base_url: 'https://generativelanguage.googleapis.com/v1beta', model: 'gemini-3.8-flash',
    docs: 'https://ai.google.dev/gemini-api/docs/video-understanding' },
}
const form = reactive({ provider: 'qwen', base_url: presets.qwen.base_url, model: presets.qwen.model, api_key: '', enabled: true })
const saved = ref(null), loading = ref(true), busy = ref(''), error = ref(''), message = ref('')
const hasSavedKey = computed(() => saved.value?.configured && saved.value.provider === form.provider && saved.value.base_url === form.base_url.trim().replace(/\/+$/, ''))
const canSubmit = computed(() => form.base_url.trim() && form.model.trim() && (form.api_key.trim() || hasSavedKey.value))
function apply(data) {
  saved.value = data
  Object.assign(form, { provider: data.provider, base_url: data.base_url, model: data.model,
    enabled: data.configured ? data.enabled : true, api_key: '' })
}
async function load() {
  loading.value = true
  error.value = ''
  try { apply(await getAiVideoSettings()) }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
onMounted(load)
function changeProvider() {
  Object.assign(form, { base_url: presets[form.provider].base_url, model: presets[form.provider].model, api_key: '' })
  error.value = ''; message.value = ''
}
async function action(kind) {
  if (busy.value) return
  busy.value = kind; error.value = ''; message.value = ''
  try {
    const payload = { ...form, api_key: form.api_key.trim() || null }
    if (kind === 'save') {
      apply(await saveAiVideoSettings(payload))
      message.value = form.enabled ? '配置已保存，可以到作品评分页发起视频分析。' : '配置已保存，视频分析已暂停。'
    } else if (kind === 'test') {
      const result = await testAiVideoSettings(payload)
      message.value = result.message + ' 修改的配置需要点击保存后生效。'
    } else {
      await deleteAiVideoSettings()
      await load()
      message.value = '已删除密钥并停止当前分析任务，历史分析结果保留。'
    }
  } catch (err) { error.value = err.message }
  finally { busy.value = '' }
}
</script>

<template>
  <div class="view-stack">
    <header v-if="!embedded" class="page-heading"><div><p class="eyebrow">AI VIDEO REVIEW</p><h1>视频辅助评阅</h1><p class="muted">连接自己的模型服务，按课程评分表分析学生的视频讲解。</p></div></header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="message" class="notice notice-success" role="status">{{ message }}</p>
    <div v-if="loading" class="skeleton-page" aria-label="正在加载配置" />
    <button v-else-if="!saved" class="button button-secondary" @click="load">重新加载</button>
    <div v-else class="ai-layout">
      <form class="ai-settings" @submit.prevent="action('save')">
        <div class="section-heading"><h2>模型连接</h2><span class="badge">{{ saved.configured ? (saved.enabled ? '已配置 · 已开启' : '已配置 · 已暂停') : '待配置' }}</span></div>
        <fieldset :disabled="!!busy">
          <label for="ai-provider">服务商</label>
          <select id="ai-provider" v-model="form.provider" @change="changeProvider"><option value="qwen">通义千问 · Qwen-Omni</option><option value="gemini">Google · Gemini</option></select>
          <label for="ai-base">接口地址 Base URL</label>
          <input id="ai-base" v-model="form.base_url" type="url" required spellcheck="false" autocomplete="off" aria-describedby="ai-base-help" />
          <small id="ai-base-help" class="muted">填写服务商控制台提供的完整 HTTPS 地址；支持使用相同接口协议的代理。千问业务空间专属地址请按控制台替换。</small>
          <label for="ai-model">模型名称</label>
          <input id="ai-model" v-model="form.model" required maxlength="128" spellcheck="false" autocomplete="off" />
          <label for="ai-key">API Key</label>
          <input id="ai-key" v-model="form.api_key" type="password" :required="!hasSavedKey" maxlength="4096" autocomplete="new-password" :placeholder="hasSavedKey ? '已保存密钥，留空表示继续使用' : '粘贴你的 API Key'" aria-describedby="ai-key-help" />
          <small id="ai-key-help" class="muted">密钥加密保存在服务器，页面不会回显。费用由该密钥所属账户承担。</small>
          <label class="ai-toggle"><input v-model="form.enabled" type="checkbox" />开启视频辅助评阅</label>
          <div class="toolbar">
            <button type="submit" class="button" :disabled="!canSubmit">{{ busy === 'save' ? '正在保存…' : '保存配置' }}</button>
            <button type="button" class="button button-secondary" :disabled="!canSubmit" @click="action('test')">{{ busy === 'test' ? '正在测试音视频接口…' : '测试视频连接' }}</button>
          </div>
          <small class="muted">连接测试会发送系统生成的两秒音视频，产生少量模型调用费用；不会发送学生材料。</small>
        </fieldset>
        <button v-if="saved.configured" type="button" class="button button-secondary button-small ai-delete" :disabled="!!busy" @click="action('delete')">删除已保存密钥并停止分析</button>
      </form>
      <aside class="ai-guide">
        <span class="service-icon"><UiIcon name="video" /></span>
        <h2>从视频到可回看的证据</h2>
        <ol><li><strong>保存连接</strong><p>选择能理解画面与声音的模型，填写密钥并测试。</p></li><li><strong>打开学生作品</strong><p>在作业评分页的材料区域，点击“分析视频”。视频将发送给所选模型服务。</p></li><li><strong>查看逐项建议</strong><p>查看内容概述、评分理由与时间点，点击证据回看原视频，再填写教师分。</p></li></ol>
        <p class="muted">支持最长 30 分钟的视频，系统按完整时长分段处理。分析结果作为教师评分参考。</p>
        <a :href="presets[form.provider].docs" target="_blank" rel="noopener noreferrer">查看服务商接入文档 ↗</a>
        <RouterLink class="button" to="/teacher/assignments">前往作业评分<UiIcon name="arrow" /></RouterLink>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.ai-layout { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(260px, .8fr); gap: 28px; align-items: start; }
.ai-settings { padding: 28px; background: var(--surface, white); border: 1px solid var(--border); border-radius: 24px; }
.ai-settings fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 10px; min-width: 0; }
.ai-settings label { font-weight: 600; margin-top: 14px; }
.ai-settings input:not([type=checkbox]), .ai-settings select { width: 100%; box-sizing: border-box; min-height: 44px; padding: 10px 12px; background: var(--surface, white); border: 1px solid var(--border); border-radius: 12px; color: inherit; }
.ai-settings small { line-height: 1.6; }
.ai-toggle { display: flex; gap: 10px; align-items: center; }
.ai-toggle input { width: 18px; height: 18px; }
.ai-delete { margin-top: 26px; }
.ai-guide { padding: 24px 8px; }
.ai-guide ol { padding-left: 22px; }
.ai-guide li { margin: 24px 0; padding-left: 6px; }
.ai-guide p { line-height: 1.7; }
.ai-guide > a { display: flex; margin-top: 24px; width: fit-content; }
@media (max-width: 850px) { .ai-layout { grid-template-columns: 1fr; } .ai-settings { padding: 20px; } }
</style>
