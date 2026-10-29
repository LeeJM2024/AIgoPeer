<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AssignmentArtwork from '../../components/AssignmentArtwork.vue'
import { assignmentTypeLabel, formatDeadline } from '../../presentation/assignments'
import { getSubjective, getSubjectiveHistory, submitSubjective } from '../../api/student/subjective'

const props = defineProps({ assignmentId: { type: [String, Number], required: true } })
const data = ref(null), content = ref(''), error = ref(''), notice = ref('')
const loading = ref(false), saving = ref(false), history = ref(null), page = ref(1)
const selected = ref(null)
const now = ref(Date.now())
const clock = setInterval(() => { now.value = Date.now() }, 1000)
let generation = 0
const closed = computed(() => !data.value || data.value.can_submit === false || !['PUBLISHED', 'SUBMITTING', 'REVIEWER_GRADING'].includes(data.value.status) ||
  (data.value.submit_deadline && new Date(data.value.submit_deadline).getTime() <= now.value))

async function load() {
  const version = ++generation, id = props.assignmentId
  loading.value = true
  error.value = ''
  try {
    const [problem, previous] = await Promise.all([getSubjective(id), getSubjectiveHistory(id, 1)])
    if (version !== generation) return
    data.value = problem
    content.value = problem.current?.content || ''
    history.value = previous
    page.value = 1
  } catch (err) { if (version === generation) error.value = err.message }
  finally { if (version === generation) loading.value = false }
}
async function turnPage(next) {
  const version = generation, id = props.assignmentId
  loading.value = true
  error.value = ''
  try {
    const result = await getSubjectiveHistory(id, next)
    if (version !== generation) return
    history.value = result
    page.value = next
  } catch (err) { if (version === generation) error.value = err.message }
  finally { if (version === generation) loading.value = false }
}
async function save() {
  if (closed.value || saving.value || !content.value.trim()) return
  const version = generation, id = props.assignmentId
  saving.value = true
  error.value = ''; notice.value = ''
  try {
    await submitSubjective(id, content.value)
    if (version !== generation) return
    await load()
    if (String(id) !== String(props.assignmentId)) return
    notice.value = error.value
      ? '答案已提交成功，但刷新失败；当前输入已保留，请重新加载确认最新版本。'
      : '答案已提交并保存为新版本，旧答案仍可在历史中查看。'
  } catch (err) { if (version === generation) error.value = err.message }
  finally { if (String(id) === String(props.assignmentId)) saving.value = false }
}
watch(() => props.assignmentId, () => {
  data.value = null; content.value = ''; selected.value = null; history.value = null
  notice.value = ''; saving.value = false
  void load()
}, { immediate: true })
onBeforeUnmount(() => { generation++; clearInterval(clock) })
</script>

<template>
  <div class="view-stack">
    <nav class="breadcrumbs"><RouterLink to="/student">我的作业</RouterLink><span>/</span><span>在线作答</span></nav>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }} <button class="text-button" :disabled="saving" @click="load">重新加载</button></p>
    <p v-if="notice" class="notice notice-success" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">正在读取题目与答案…</p>
    <template v-if="data">
      <header class="page-heading"><div><p>{{ assignmentTypeLabel(data.type) }}</p><h1>{{ data.title }}</h1><p>提交截止：{{ formatDeadline(data.submit_deadline) }}</p></div></header>
      <div class="answer-layout">
        <section class="data-section question">
          <figure><AssignmentArtwork :assignment="data" /><figcaption>课程示意 · 非标准答案</figcaption></figure>
          <h2>题目要求</h2><p class="preserve-lines">{{ data.statement }}</p>
          <p v-if="data.topics.length">知识点：{{ data.topics.map(t => t.name).join('、') }}</p>
          <p class="muted">提交答案即可完成本题，无需教师评分或同伴评审。</p>
        </section>
        <form class="editor-panel" @submit.prevent="save">
          <h2>你的答案</h2>
          <p id="answer-help" class="muted">支持纯文本、公式和伪代码。提交后可在截止前修改答案，历史版本会保留。</p>
          <p v-if="closed" class="notice" role="status">已停止接收答案；当前提交及历史版本仍可查看。</p>
          <label for="subjective-content">作答内容</label>
          <textarea id="subjective-content" v-model="content" rows="20" required maxlength="50000" aria-describedby="answer-help" :readonly="closed" :disabled="saving" />
          <div class="form-actions"><small>{{ content.length }} / 50000 字符 · {{ data.current ? `当前 v${data.current.version}` : '尚未提交' }}</small><button class="button" :disabled="closed || saving || loading || !content.trim()">{{ saving ? '正在提交…' : '提交新版本' }}</button></div>
        </form>
      </div>
      <section class="data-section" aria-label="在线答案提交历史">
        <h2>提交历史</h2>
        <p v-if="!history?.total" class="muted">尚无提交记录。</p>
        <div v-else class="table-wrap"><table><thead><tr><th>版本</th><th>提交时间</th><th>查看</th></tr></thead><tbody>
          <tr v-for="item in history.items" :key="item.id"><td>v{{ item.version }} {{ item.is_current ? '· 当前' : '' }}</td><td>{{ formatDeadline(item.submitted_at) }}</td><td><button class="text-button" @click="selected = item">查看答案 v{{ item.version }}</button></td></tr>
        </tbody></table></div>
        <nav v-if="history?.total > 10" class="toolbar" aria-label="答案历史分页"><button class="button button-secondary" :disabled="page <= 1 || loading" @click="turnPage(page - 1)">上一页</button><span>第 {{ page }} 页 · {{ history.total }} 条</span><button class="button button-secondary" :disabled="page * 10 >= history.total || loading" @click="turnPage(page + 1)">下一页</button></nav>
        <section v-if="selected"><h3>历史答案 v{{ selected.version }}</h3><pre>{{ selected.content }}</pre></section>
      </section>
    </template>
  </div>
</template>

<style scoped>
.answer-layout { display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); gap: 24px; align-items: start; }
.answer-layout > * { min-width: 0; }
.question figure { margin: 0 0 24px; background: var(--art-gradient); border-radius: 26px 60px 26px 26px; padding: 16px; }
.question figure .assignment-artwork { width: 100%; height: 180px; }
figcaption { text-align: center; font-size: 12px; color: var(--muted); }
.preserve-lines, pre { white-space: pre-wrap; overflow-wrap: anywhere; }
textarea { width: 100%; min-height: 320px; font: 15px/1.8 Consolas, 'Microsoft YaHei', monospace; }
.form-actions { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; justify-content: space-between; margin-top: 16px; }
pre { padding: 20px; background: var(--surface-subtle); border-radius: 18px; max-height: 480px; overflow: auto; }
@media (max-width: 900px) { .answer-layout { grid-template-columns: minmax(0, 1fr); } }
</style>
