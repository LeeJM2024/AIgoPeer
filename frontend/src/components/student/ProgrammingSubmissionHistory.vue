<script setup>
import { computed, onMounted, ref } from 'vue'
import { getCodeSubmission, getCodeSubmissionHistory } from '../../api/student/programmingSubmissions'
import ProgrammingSubmissionResult from './ProgrammingSubmissionResult.vue'

const props = defineProps({
  assignmentId: { type: String, required: true },
  latestResult: { type: Object, default: null },
})
const emit = defineEmits(['current'])
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 5
const loading = ref(false)
const error = ref('')
const selectedId = ref(null)
const selectedResult = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
let detailRequest = 0
let historyRequest = 0
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const rows = computed(() => items.value.map((item) =>
  props.latestResult?.id === item.id ? { ...item, status: props.latestResult.status } : item))
const pendingDetail = computed(() => ['QUEUED', 'RUNNING'].includes(selectedResult.value?.status))
const formatTime = (value) => new Date(value).toLocaleString('zh-CN')
const statusName = (status) => ({
  QUEUED: '排队中', RUNNING: '判题中', AC: '通过', WA: '答案错误',
  CE: '编译错误', RE: '运行错误', TLE: '超出时间限制', SYSTEM_ERROR: '判题系统异常',
}[status] ?? status)

async function refresh(resetPage = false, targetPage = page.value) {
  const request = ++historyRequest
  loading.value = true
  error.value = ''
  try {
    const data = await getCodeSubmissionHistory(props.assignmentId, resetPage ? 1 : targetPage, pageSize)
    if (request !== historyRequest) return
    items.value = data.items
    total.value = data.total
    page.value = data.page
    const current = data.items.find((item) => item.is_current)
    if (current) emit('current', current)
  } catch (err) {
    if (request === historyRequest) error.value = err.message
  } finally {
    if (request === historyRequest) loading.value = false
  }
}

async function changePage(nextPage) {
  await refresh(false, nextPage)
}

async function selectResult(id) {
  const request = ++detailRequest
  selectedId.value = id
  selectedResult.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const result = await getCodeSubmission(id)
    if (request === detailRequest) selectedResult.value = result
  } catch (err) {
    if (request === detailRequest) detailError.value = err.message
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
}

onMounted(refresh)
defineExpose({ refresh })
</script>

<template>
  <section class="submission-history" aria-labelledby="submission-history-title">
    <header class="history-heading">
      <div><h2 id="submission-history-title">提交历史</h2><p>查看本题历次提交的判题结果。历史记录只读。</p></div>
      <button type="button" :disabled="loading" @click="refresh()">{{ loading ? '正在刷新…' : '刷新提交历史' }}</button>
    </header>
    <p v-if="error" class="history-error" role="alert">历史加载失败：{{ error }}</p>
    <p v-if="loading" role="status">正在加载提交历史…</p>
    <p v-else-if="!error && total === 0">暂无提交记录。</p>
    <template v-if="rows.length">
      <div class="history-table-wrap">
        <table>
          <caption>共 {{ total }} 次提交 · 最新版本在前</caption>
          <thead><tr><th>版本</th><th>提交时间</th><th>判题状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="item in rows" :key="item.id" :class="{ selected: selectedId === item.id }">
              <td>第 {{ item.version }} 次<span v-if="item.is_current" class="current-tag">当前版本</span></td>
              <td>{{ formatTime(item.submitted_at) }}</td>
              <td>{{ statusName(item.status) }}</td>
              <td><button type="button" :aria-pressed="selectedId === item.id" :aria-label="`查看第 ${item.version} 次提交结果`" @click="selectResult(item.id)">查看结果</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav class="history-pagination" aria-label="提交历史分页">
        <button type="button" :disabled="loading || page <= 1" @click="changePage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <button type="button" :disabled="loading || page >= pageCount" @click="changePage(page + 1)">下一页</button>
      </nav>
    </template>
    <section v-if="selectedId" class="history-detail" aria-label="历史判题详情">
      <h3>历史判题详情</h3>
      <p>查看此记录不会替换编辑器中的代码。</p>
      <p v-if="detailLoading" role="status">正在加载判题详情…</p>
      <div v-else-if="detailError" class="history-error" role="alert">
        <p>{{ detailError }}</p><button type="button" @click="selectResult(selectedId)">重试判题详情</button>
      </div>
      <ProgrammingSubmissionResult v-else-if="selectedResult" :submission="selectedResult" :polling-stopped="pendingDetail" :is-refreshing="detailLoading" @refresh="selectResult(selectedId)" />
    </section>
  </section>
</template>

<style scoped>
.submission-history { margin-top: 24px; padding: 22px; border: 1px solid #cfe2d6; border-radius: 12px; background: #fff; color: #163b31; }
.history-heading { display: flex; gap: 16px; justify-content: space-between; align-items: start; }.history-heading h2 { margin: 0; }.history-heading p, .history-detail > p { color: #365f52; }
button { padding: 8px 12px; border: 1px solid #5e8874; border-radius: 6px; color: #174d38; background: #f4faf6; cursor: pointer; }button:disabled { opacity: .55; cursor: not-allowed; }
.history-table-wrap { overflow-x: auto; }table { width: 100%; border-collapse: collapse; text-align: left; }caption { padding: 12px 0; text-align: left; color: #365f52; }th, td { padding: 12px 8px; border-bottom: 1px solid #dce9e1; }th { background: #f4faf6; }tr.selected { background: #e8f5ed; }
.current-tag { display: inline-block; margin-left: 8px; padding: 3px 6px; border-radius: 4px; background: #d5efdf; color: #174d38; font-size: 12px; }.history-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 12px; margin-top: 16px; }
.history-detail { margin-top: 22px; }.history-detail .result { color: #e8f2ed; }.history-error { color: #982a31; }@media (max-width: 760px) { .history-heading { flex-direction: column; }th, td { padding: 10px 6px; } }
</style>
