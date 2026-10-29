<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { getEvidence, getSubjectiveAnswers } from '../../api/teacher'
import { formatDeadline } from '../../presentation/assignments'

const props = defineProps({ assignmentId: { type: Number, required: true } })
const data = ref(null), loading = ref(false), error = ref(''), page = ref(1)
const selected = ref(null), answer = ref(null), answerError = ref('')
let generation = 0, answerGeneration = 0
async function load(next = page.value) {
  const request = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await getSubjectiveAnswers(props.assignmentId, next)
    if (request !== generation) return
    data.value = result
    page.value = next
  } catch (err) { if (request === generation) error.value = err.message }
  finally { if (request === generation) loading.value = false }
}
async function open(row, version) {
  const request = ++answerGeneration
  selected.value = { name: row.name, version: version.version }
  answer.value = null
  answerError.value = ''
  try {
    const result = await getEvidence(version.id)
    if (request === answerGeneration) answer.value = result.answer
  } catch (err) { if (request === answerGeneration) answerError.value = err.message }
}
function close() { answerGeneration++; selected.value = null }
watch(() => props.assignmentId, () => {
  data.value = null
  close()
  void load(1)
}, { immediate: true })
onBeforeUnmount(() => { generation++; answerGeneration++ })
</script>

<template>
  <section class="data-section" aria-label="学生作答情况">
    <div class="section-heading"><h2>学生作答情况</h2><button class="button button-secondary button-small" :disabled="loading" @click="load()">刷新</button></div>
    <p>提交答案即可完成本题，无需教师评分或同伴评审。</p>
    <p v-if="data">{{ data.submitted }} 人已提交 · {{ data.total - data.submitted }} 人未提交 · 共 {{ data.total }} 人</p>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在读取提交情况…</p>
    <div v-if="data?.items.length" class="table-wrap"><table>
      <thead><tr><th>学生</th><th>班级</th><th>提交状态</th><th>提交时间</th><th>答案与历史</th></tr></thead>
      <tbody><tr v-for="row in data.items" :key="row.student_id">
        <td>{{ row.name }}<small>{{ row.student_no }}</small></td>
        <td>{{ row.class_name }}</td><td>{{ row.submission_id ? `已完成 · v${row.version}` : '未提交' }}</td>
        <td>{{ row.submitted_at ? formatDeadline(row.submitted_at) : '—' }}</td>
        <td><template v-if="row.versions.length"><button class="text-button" @click="open(row, row.versions[0])">查看答案</button>
          <details v-if="row.versions.length > 1"><summary>历史版本（{{ row.versions.length }}）</summary>
            <button v-for="version in row.versions" :key="version.id" class="text-button version-button" @click="open(row, version)">v{{ version.version }} · {{ formatDeadline(version.submitted_at) }}</button>
          </details></template><span v-else>—</span></td>
      </tr></tbody>
    </table></div>
    <p v-else-if="data && !loading" class="muted">适用班级中暂无学生。</p>
    <nav v-if="data?.total > 20" class="toolbar" aria-label="作答情况分页">
      <button class="button button-secondary" :disabled="loading || page <= 1" @click="load(page - 1)">上一页</button>
      <span>第 {{ page }} 页 · 共 {{ data.total }} 人</span>
      <button class="button button-secondary" :disabled="loading || page * 20 >= data.total" @click="load(page + 1)">下一页</button>
    </nav>
    <section v-if="selected" class="answer-preview" aria-label="学生答案预览">
      <div class="section-heading"><h3>{{ selected.name }} · 答案 v{{ selected.version }}</h3><button class="text-button" @click="close">关闭答案</button></div>
      <p v-if="answerError" class="notice notice-error" role="alert">{{ answerError }}</p>
      <p v-else-if="answer === null" role="status">正在读取答案…</p>
      <pre v-else>{{ answer }}</pre>
    </section>
  </section>
</template>

<style scoped>
td small { display: block; color: var(--muted); margin-top: 6px; }
.version-button { display: block; margin: 8px 0; }
.answer-preview { margin-top: 24px; border-top: 1px solid var(--line); padding-top: 20px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 520px; overflow: auto; line-height: 1.8; }
</style>
