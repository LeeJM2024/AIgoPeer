<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { getClasses, getLearningAnalysis } from '../../api/teacher'
import { assignmentTypeLabel } from '../../presentation/assignments'

const route = useRoute(), router = useRouter()
const data = ref(null), classes = ref([]), loading = ref(false), error = ref('')
const classId = ref(String(route.query.class_id || ''))
let generation = 0
const percent = value => value == null ? '暂无数据' : `${(value * 100).toFixed(1)}%`
const errorLabel = value => ({ WA: '答案错误', TLE: '超时', RE: '运行错误', CE: '编译错误' })[value] || value
async function load() {
  const version = ++generation
  loading.value = true; error.value = ''; data.value = null
  try {
    const [report, options] = await Promise.all([getLearningAnalysis(classId.value), getClasses()])
    if (version !== generation) return
    data.value = report; classes.value = options
  } catch (err) { if (version === generation) error.value = err.message }
  finally { if (version === generation) loading.value = false }
}
function changeClass() {
  router.replace({ query: classId.value ? { class_id: classId.value } : {} })
}
watch(() => route.query.class_id, value => { classId.value = String(value || ''); void load() })
onMounted(load)
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <div class="view-stack">
    <header class="page-heading"><div><p class="muted">课程学习档案</p><h1>学习过程分析</h1><p>从提交轨迹、常见错误到知识点表现，定位需要讲解和练习的内容。</p></div><button class="button button-secondary" :disabled="loading" @click="load">{{ loading ? '正在刷新…' : '刷新数据' }}</button></header>
    <label class="analysis-filter">查看班级<select v-model="classId" :disabled="loading" @change="changeClass"><option value="">全部班级</option><option v-for="item in classes" :key="item.id" :value="String(item.id)">{{ item.name }} · {{ item.course_term }}</option></select></label>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }} <button class="text-button" @click="load">重试</button></p>
    <p v-if="loading" role="status">正在汇总真实提交与已发布成绩…</p>
    <template v-if="data">
      <section class="metric-strip" aria-label="分析概况"><div><span>已发布作业</span><strong>{{ data.assignment_count }}</strong><small>不含草稿</small></div><div><span>编程提交</span><strong>{{ data.code_attempt_count }}</strong><small>含历史尝试</small></div><div><span>知识点</span><strong>{{ data.topics.length }}</strong><small>已标记或认领的主题</small></div></section>
      <section class="data-section"><h2>题目表现与提交过程</h2><p class="muted">AC 率按“曾通过人数 / 已有有效判题人数”计算；描述性难度 = 1 − AC率，未提交人数另列。证明题、开放问答题和算法分析题只统计提交，不计分。</p>
        <div v-if="data.assignments.length" class="table-wrap"><table><thead><tr><th>作业 / 类型</th><th>已提交 / 在籍 · 未提交</th><th>总尝试 / 人均尝试</th><th>曾 AC / 已判题 · 当前 AC</th><th>AC率 / 难度</th><th>平均耗时 / 峰值内存</th><th>期末作业已发布 / 均分</th></tr></thead><tbody>
          <tr v-for="row in data.assignments" :key="row.id"><td><RouterLink :to="`/teacher/assignments/${row.id}`">{{ row.title }}</RouterLink><small>{{ assignmentTypeLabel(row.type) }}</small></td><td>{{ row.submitted_students }} / {{ row.enrolled_students }}<small>未提交 {{ row.unsubmitted_students }}</small></td><td>{{ row.submission_count }}<small>{{ row.average_attempts ?? '—' }}</small></td><td>{{ row.passed_students ?? '—' }} / {{ row.judged_students ?? '—' }}<small>当前 AC {{ row.current_passed_students ?? '—' }}</small></td><td>{{ row.type === 'PROGRAMMING' ? percent(row.ac_rate) : '不适用' }}<small>{{ row.type === 'PROGRAMMING' ? percent(row.difficulty) : '—' }}</small></td><td>{{ row.average_time_ms ?? '—' }} ms<small>{{ row.peak_memory_kb ?? '—' }} KiB</small></td><td>{{ row.type !== 'FINAL_PROJECT' ? '不适用' : `${row.published_count} 份` }}<small v-if="row.type === 'FINAL_PROJECT'">{{ row.average_score ?? '—' }} / {{ row.maximum_score }}</small></td></tr>
        </tbody></table></div><p v-else class="empty-state">当前范围暂无已发布作业。</p>
      </section>
      <section class="data-section"><h2>常见编程错误</h2><p class="muted">统计全部历史有效判题中的错误次数。系统故障与排队不作为学生错误。</p>
        <div v-if="Object.keys(data.error_counts).length" class="error-summary"><div v-for="(count, status) in data.error_counts" :key="status"><strong>{{ errorLabel(status) }}</strong><span>{{ count }} 次</span></div></div><p v-else class="muted">暂无已判定的编程错误记录。</p>
        <details v-for="row in data.assignments.filter(item => item.type === 'PROGRAMMING')" :key="row.id"><summary>{{ row.title }} · 查看错误、排队和故障明细</summary><p>{{ Object.entries(row.error_counts).map(([status, count]) => `${errorLabel(status)} ${count} 次`).join(' · ') || '无代码错误' }}</p><p>排队 / 运行中 {{ row.pending_count }} 次；系统故障 {{ row.system_errors }} 次。</p></details>
      </section>
      <section class="data-section"><h2>知识点掌握情况 · 观察指标</h2><p class="muted">仅使用当前有效判题或已发布成绩，按学生—作业等权汇总，不是能力预测。多知识点作业的整体表现计入各关联点，不能解释为独立考查结果。</p>
        <div v-if="data.topics.length" class="table-wrap"><table><thead><tr><th>知识点</th><th>观察掌握率</th><th>有效样本</th><th>学生 / 作业数</th></tr></thead><tbody><tr v-for="topic in data.topics" :key="topic.id"><td>{{ topic.code }} · {{ topic.name }}</td><td>{{ percent(topic.mastery) }}</td><td>{{ topic.evidence_count }} 个学生—作业样本</td><td>{{ topic.student_count }} 人 / {{ topic.assignment_count }} 份</td></tr></tbody></table></div><p v-else class="muted">暂无关联知识点。新建作业时可标记知识点；旧作业不会被自动猜测分类。</p>
      </section>
      <details class="data-section"><summary>统计口径与更新时间</summary><p v-for="(definition, key) in data.definitions" :key="key">{{ definition }}</p><p>更新时间：{{ new Date(data.generated_at).toLocaleString('zh-CN') }}</p></details>
    </template>
  </div>
</template>

<style scoped>
.analysis-filter { max-width: 360px; }
td small { display: block; margin-top: 6px; color: var(--muted); }
th { white-space: nowrap; }
.error-summary { display: flex; flex-wrap: wrap; gap: 14px 36px; padding: 12px 0 20px; }
.error-summary > div { display: flex; gap: 18px; align-items: baseline; }
.error-summary span { color: var(--primary); font-size: 22px; font-variant-numeric: tabular-nums; }
details { margin-top: 12px; } summary { cursor: pointer; padding: 10px 0; }
</style>
