<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getProgrammingHistory } from '../../api/teacher'
const props = defineProps({ assignmentId: { type: Number, required: true }, students: { type: Array, default: () => [] } })
const history = ref(null), page = ref(1), studentId = ref(''), selected = ref(null), loading = ref(false), error = ref('')
const choices = computed(() => Array.from(new Map(props.students.map(item => [item.id, item])).values()))
const names = { AC: '通过', WA: '答案错误', TLE: '超时', RE: '运行错误', CE: '编译错误', QUEUED: '排队中', RUNNING: '运行中', SYSTEM_ERROR: '系统故障' }
let generation = 0
async function load(next = 1) {
  const version = ++generation
  loading.value = true; error.value = ''; selected.value = null
  try {
    const result = await getProgrammingHistory(props.assignmentId, next, studentId.value)
    if (version !== generation) return
    history.value = result; page.value = next
  } catch (err) { if (version === generation) { history.value = null; error.value = err.message } }
  finally { if (version === generation) loading.value = false }
}
watch(() => props.assignmentId, () => { studentId.value = ''; history.value = null; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section class="data-section" aria-label="教师编程提交历史">
    <div class="section-heading"><div><h2>完整提交历史</h2><p>查看每次尝试的源码、编译反馈、运行资源与结果，不只显示当前版本。</p></div><button class="button button-secondary" :disabled="loading" @click="load(page)">刷新历史</button></div>
    <label>筛选学生<select v-model="studentId" :disabled="loading" @change="load(1)"><option value="">全部学生</option><option v-for="item in choices" :key="item.id" :value="item.id">{{ item.student_no }} · {{ item.name }}</option></select></label>
    <p v-if="loading" role="status">正在读取提交历史…</p><p v-if="error" role="alert" class="notice notice-error">{{ error }} <button class="text-button" @click="load(page)">重试</button></p>
    <div v-if="history?.items.length" class="table-wrap"><table><thead><tr><th>学生 / 班级</th><th>版本 / 时间</th><th>判题结果</th><th>耗时 / 内存</th><th>详情</th></tr></thead><tbody><tr v-for="row in history.items" :key="row.id"><td>{{ row.student_no }} · {{ row.name }}<small>{{ row.class_name }}</small></td><td>v{{ row.version }} {{ row.is_current ? '· 当前' : '' }}<small>{{ new Date(row.queued_at).toLocaleString('zh-CN') }}</small></td><td>{{ names[row.status] || row.status }}<small>{{ row.passed_case_count }} / {{ row.executed_case_count }} 用例</small></td><td>{{ row.time_ms ?? '—' }} ms<small>{{ row.memory_kb ?? '—' }} KiB</small></td><td><button class="text-button" @click="selected = row">查看提交 {{ row.id }}</button></td></tr></tbody></table></div>
    <p v-else-if="history && !loading" class="muted">当前筛选下暂无提交记录。</p>
    <nav v-if="history?.total" class="toolbar" aria-label="编程历史分页"><button class="button button-secondary" :disabled="page <= 1 || loading" @click="load(page - 1)">上一页</button><span>第 {{ page }} 页 · 共 {{ history.total }} 次</span><button class="button button-secondary" :disabled="page * 20 >= history.total || loading" @click="load(page + 1)">下一页</button></nav>
    <section v-if="selected" class="submission-detail"><h3>{{ selected.student_no }} · v{{ selected.version }} · {{ names[selected.status] }}</h3><p>开始：{{ selected.started_at ? new Date(selected.started_at).toLocaleString('zh-CN') : '—' }} · 完成：{{ selected.finished_at ? new Date(selected.finished_at).toLocaleString('zh-CN') : '—' }}</p><h4>提交源码</h4><pre>{{ selected.source_code }}</pre><h4>编译反馈</h4><pre>{{ selected.compiler_output || '无编译错误输出' }}</pre><button class="text-button" @click="selected = null">关闭详情</button></section>
  </section>
</template>
<style scoped>
label { max-width: 360px; } small { display: block; color: var(--muted); margin-top: 6px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 420px; overflow: auto; background: var(--code-bg); color: var(--code-ink); border-radius: 18px; padding: 20px; }
.submission-detail { margin-top: 24px; } nav { margin-top: 18px; }
</style>
