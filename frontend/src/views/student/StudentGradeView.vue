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
.grade-page { display: grid; grid-template-columns: minmax(0,1fr); gap: 20px; }
.grade-page > * { min-width: 0; }
.grade-page h1 { margin: -12px 0 0; }
.back-link { width: fit-content; min-height: 32px; display: inline-flex; align-items: center; color: var(--muted); font-size: 12px; text-decoration: none; }
.back-link:hover { color: var(--primary); }
.eyebrow { margin: 0; color: var(--primary); font-size: 12px; font-weight: 600; }
.score-card { display: grid; gap: 14px; padding: 28px; border: 1px solid #cee3df; border-radius: var(--radius); color: var(--primary-hover); background: var(--primary-soft); }
.score-card > span { font-size: 13px; }
.score-card strong { font-size: 48px; line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: -1px; }
.score-card small { font-size: 12px; color: var(--muted); }
.card h2 { margin-bottom: 10px; }
.card > p { margin-bottom: 0; }
.empty-state { padding: 24px; border: 1px solid var(--border); background: var(--surface); }
.rubric-list, .comment-list { display: grid; gap: 12px; padding: 0; list-style: none; margin-bottom: 0; }
.rubric-list li { display: block; padding: 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface-subtle); }
.rubric-list strong { font-size: 14px; }
.rubric-list li > span { display: inline; width: auto; height: auto; padding: 0; border-radius: 0; float: right; background: none; color: var(--muted); font-size: 12px; font-weight: 400; }
.rubric-list p { clear: both; margin: 8px 0 0; color: var(--muted); font-size: 13px; }
.comment-list li { padding: 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface-subtle); line-height: 1.8; overflow-wrap: anywhere; }
</style>
