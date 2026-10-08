<script setup>
import { onMounted, ref } from 'vue'
import { getAiVideoStatus } from '../../api/teacher'
const status = ref(null); const error = ref('')
onMounted(async () => { try { status.value = await getAiVideoStatus() } catch (err) { error.value = err.message } })
</script>

<template>
  <div class="view-stack narrow-view"><header class="page-heading"><div><p class="section-label">辅助能力</p><h1>视频智能分析</h1><p>模型只生成建议分和证据，正式教师分必须由教师确认。</p></div></header><p v-if="error" class="notice notice-error">{{ error }}</p>
    <section class="readiness-panel"><div><span class="status-dot" :class="{ ready: status?.enabled }" /><h2>{{ status?.enabled ? '视频分析服务已启用' : '尚未启用视频分析服务' }}</h2><p v-if="status?.configured && !status.enabled">服务已配置，但功能开关仍关闭。</p><p v-else-if="!status?.configured">这是安全的默认状态，不影响视频播放和人工评分。</p></div><dl><div><dt>服务商</dt><dd>{{ status?.provider || '未配置' }}</dd></div><div><dt>模型</dt><dd>{{ status?.model || '未配置' }}</dd></div><div><dt>API 密钥</dt><dd>{{ status?.configured ? '已由服务器安全保存' : '未配置' }}</dd></div></dl></section>
    <section class="data-section"><div class="section-heading"><div><h2>为什么不在这里填写 API Key</h2><p>浏览器不是保存课程密钥的安全位置。</p></div></div><div class="prose"><p>部署管理员通过服务器环境变量或密钥管理服务配置 <code>AI_VIDEO_PROVIDER</code>、<code>AI_VIDEO_API_KEY</code> 和 <code>AI_VIDEO_MODEL</code>。教师端只能查看是否就绪，永远无法读取完整密钥。</p><p>后端已经预留供应商中立的适配层和独立分析记录。更换模型不会改写历史教师分，也不会把学生视频暴露成公开链接。</p></div></section>
    <section class="workflow-list"><h2>分析结果进入成绩前的四道边界</h2><ol><li><span>1</span><div><strong>材料处理</strong><p>私有存储、格式检查、转码和文件哈希。</p></div></li><li><span>2</span><div><strong>证据提取</strong><p>转写、关键帧、OCR 和对应时间点。</p></div></li><li><span>3</span><div><strong>Rubric 建议</strong><p>建议分、置信度、理由和待复核项。</p></div></li><li><span>4</span><div><strong>教师确认</strong><p>只有明确保存和锁定后才成为教师分。</p></div></li></ol></section>
  </div>
</template>
