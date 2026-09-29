<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { createTeacherGrade, correctTeacherGrade, getGradingWorkspace, lockTeacherGrade, publishResults } from '../../api/teacher'

const route = useRoute(); const id = Number(route.params.id); const data = ref(null); const selectedId = ref(null); const correctionMode = ref(false); const form = reactive({ scores: {}, comment: '', reason: '' }); const error = ref(''); const notice = ref(''); const busy = ref(false)
const selected = computed(() => data.value?.submissions.find(s => s.id === selectedId.value))
async function load() { try { data.value = await getGradingWorkspace(id); if (!selectedId.value && data.value.submissions.length) select(data.value.submissions[0]) } catch (err) { error.value = err.message } }
onMounted(load)
function select(item) { selectedId.value = item.id; correctionMode.value = false; form.scores = {}; data.value.rubric_items.forEach(r => form.scores[r.id] = item.rubric_scores_json?.[r.id] ?? ''); form.comment = item.feedback || ''; form.reason = '' }
const total = computed(() => Object.values(form.scores).reduce((n, v) => n + (Number(v) || 0), 0))
async function save() { busy.value = true; error.value = ''; try { const payload = { rubric_scores: data.value.rubric_items.map(r => ({ rubric_item_id: r.id, score: Number(form.scores[r.id]) })), comment: form.comment }; if (correctionMode.value) await correctTeacherGrade(selected.value.id, { ...payload, reason: form.reason }); else await createTeacherGrade(selected.value.id, payload); notice.value = correctionMode.value ? '更正版本已创建，请核对后锁定。' : '评分已保存，锁定前请再次核对。'; await load(); select(data.value.submissions.find(s => s.id === selectedId.value)) } catch (err) { error.value = err.message } finally { busy.value = false } }
function beginCorrection() { correctionMode.value = true; notice.value = '正在创建新版本；原评分会完整保留。' }
async function lock() { if (!confirm('锁定后不能原地修改。确认锁定这份教师评分吗？')) return; busy.value = true; try { await lockTeacherGrade(selected.value.teacher_grade_id); notice.value = '教师评分已锁定。'; await load() } catch (err) { error.value = err.message } finally { busy.value = false } }
async function publishAll() { if (!confirm('确认发布全部学生的最终成绩吗？发布后学生即可查看。')) return; busy.value = true; try { const result = await publishResults(id); notice.value = `已发布 ${result.published_count} 份成绩。`; await load() } catch (err) { error.value = err.message } finally { busy.value = false } }
</script>

<template>
  <div v-if="data" class="view-stack grading-page">
    <nav class="breadcrumbs"><RouterLink :to="`/teacher/assignments/${id}`">{{ data.assignment.title }}</RouterLink><span>/</span><span>评分工作台</span></nav>
    <header class="page-heading"><div><p class="section-label">教师独立评分</p><h1>评分工作台</h1><p>算法聚合结果仅作参考；教师评分由你明确保存并锁定。</p></div><button class="button" :disabled="busy || data.assignment.status === 'PUBLISHED_RESULT'" @click="publishAll">发布全部成绩</button></header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p><p v-if="notice" class="notice notice-success" role="status">{{ notice }}</p>
    <div class="grading-layout"><aside class="submission-index" aria-label="学生提交列表"><button v-for="item in data.submissions" :key="item.id" :class="{ selected: item.id === selectedId }" @click="select(item)"><span><strong>{{ item.author_name }}</strong><small>{{ item.student_no }} · {{ item.class_name }}</small></span><span class="grade-state">{{ item.published_at ? '已发布' : item.locked_at ? '已锁定' : item.teacher_grade_id ? '待锁定' : '未评分' }}</span></button><div v-if="!data.submissions.length" class="empty-state compact">暂无有效提交</div></aside>
      <section v-if="selected" class="grading-editor"><div class="student-summary"><div><h2>{{ selected.author_name }}</h2><p>{{ selected.student_no }} · 匿名编号 {{ selected.anonymous_token }}</p></div><div class="score-comparison"><span>同伴聚合<strong>{{ selected.aggregate_score ?? '待生成' }}</strong></span><span>教师当前分<strong>{{ selected.teacher_score ?? '—' }}</strong></span><span v-if="selected.open_anomaly_count" class="attention">异常<strong>{{ selected.open_anomaly_count }}</strong></span></div></div>
        <div class="evidence-placeholder"><strong>视频与材料证据区</strong><p>接入学生上传模块后，这里显示私有视频、转写稿、时间点证据和 AI 建议；AI 不会直接写入下方评分。</p></div>
        <form @submit.prevent="save"><div class="score-sheet"><label v-for="rubric in data.rubric_items" :key="rubric.id"><span><strong>{{ rubric.name }}</strong><small>{{ rubric.description }}</small></span><span class="score-input"><input v-model="form.scores[rubric.id]" type="number" min="0" :max="rubric.max_score" step="0.5" :disabled="Boolean(selected.teacher_grade_id) && !correctionMode" required /><b>/ {{ rubric.max_score }}</b></span></label></div><label>教师反馈<textarea v-model="form.comment" rows="4" :disabled="Boolean(selected.teacher_grade_id) && !correctionMode" placeholder="说明做得好的地方和需要改进的内容"></textarea></label><label v-if="correctionMode">更正原因<input v-model="form.reason" required minlength="3" placeholder="创建新版本时必须说明原因" /></label><div class="form-actions"><div class="total-score">本次合计 <strong>{{ total }}</strong></div><button v-if="!selected.teacher_grade_id || correctionMode" class="button" :disabled="busy">{{ correctionMode ? '保存更正版本' : '保存教师评分' }}</button><button v-if="selected.teacher_grade_id && !selected.locked_at && !correctionMode" class="button button-secondary" type="button" :disabled="busy" @click="lock">锁定当前评分</button><button v-if="selected.locked_at && !correctionMode" class="button button-secondary" type="button" :disabled="busy" @click="beginCorrection">创建更正版本</button><span v-if="selected.locked_at && !correctionMode" class="locked-label">当前版本已锁定</span></div></form>
      </section></div>
  </div>
  <div v-else class="view-stack"><p v-if="error" class="notice notice-error">加载失败：{{ error }}</p><div v-else class="skeleton-page" /></div>
</template>
