<script setup>
import { onMounted, ref } from 'vue'

import { getMyPublishedGrade } from '../../api/student/grades'

const props = defineProps({ assignmentId: { type: [String, Number], required: true } })
const grade = ref(null)
const error = ref('')
const loading = ref(false)

async function loadGrade() {
  loading.value = true
  error.value = ''
  try { grade.value = await getMyPublishedGrade(props.assignmentId) }
  catch (err) { error.value = err.status === 403 ? '成绩暂未发布。' : err.message }
  finally { loading.value = false }
}

onMounted(loadGrade)
</script>

<template>
  <section class="grade-page">
    <RouterLink class="back-link" to="/student">← 返回我的作业</RouterLink>
    <p class="eyebrow">个人成绩反馈</p>
    <h1>最终成绩</h1>
    <p v-if="loading" class="muted">正在读取成绩…</p>
    <p v-else-if="error" class="empty-state">{{ error }}</p>
    <template v-else-if="grade">
      <div class="score-card"><span>最终总分</span><strong>{{ grade.final_score }}</strong><small>发布于 {{ new Date(grade.published_at).toLocaleString('zh-CN') }}</small></div>
      <section class="card"><h2>评价维度</h2><p class="muted">以下为课程评分依据说明，不展示教师原始分、聚合分或各维度具体分数。</p><ul class="rubric-list"><li v-for="item in grade.rubric_items" :key="item.sort_order"><strong>{{ item.name }}</strong><span>满分 {{ item.max_score }}</span><p>{{ item.description || '按课程 Rubric 进行评价。' }}</p></li></ul></section>
      <section class="card"><h2>匿名评语汇总</h2><p v-if="!grade.anonymous_comments.length" class="muted">暂无可展示的匿名评语。</p><ul v-else class="comment-list"><li v-for="(item,index) in grade.anonymous_comments" :key="index">{{ item }}</li></ul></section>
      <section class="card"><h2>教师反馈</h2><p>{{ grade.teacher_feedback || '暂无教师反馈。' }}</p></section>
    </template>
  </section>
</template>

<style scoped>
.grade-page { display:grid; gap:20px; }.grade-page h1 { margin:-12px 0 0; }.back-link { width:max-content; text-decoration:none; }.eyebrow { margin:0; color:#276749; font-size:13px; font-weight:750; }.score-card { display:grid; gap:5px; padding:28px; border-radius:14px; color:#ecfaf1; background:linear-gradient(125deg,#063a2b,#0d5a42); }.score-card strong { font-size:52px; line-height:1; }.score-card small { color:#c9e6d4; }.card { padding:24px; border:1px solid #d5e3da; border-radius:12px; background:#fff; }.card h2 { margin-bottom:10px; }.muted { color:#61756a; }.empty-state { padding:22px; border:1px dashed #a6bfaf; border-radius:9px; color:#61756a; }.rubric-list,.comment-list { display:grid; gap:12px; padding:0; list-style:none; }.rubric-list li { padding:14px; border-radius:8px; background:#f4f9f6; }.rubric-list span { float:right; color:#38634c; font-size:13px; }.rubric-list p { clear:both; margin:8px 0 0; color:#61756a; }.comment-list li { padding:14px; border-left:3px solid #6fa684; background:#f7faf8; line-height:1.6; }
</style>
