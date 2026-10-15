<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getMaterialCheck, getProjectSubmissionHistory } from '../../api/student/projectSubmissions'

const props = defineProps({
  assignmentId: { type: [String, Number], required: true },
  latestSubmission: { type: Object, default: null },
  latestCheck: { type: Object, default: null },
})
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 5
const loading = ref(false)
const error = ref('')
const selected = ref(null)
const selectedCheck = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
let historyRequest = 0
let detailRequest = 0
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const rows = computed(() => items.value.map((item) => {
  if (item.is_current && props.latestSubmission?.id === item.id && props.latestCheck) {
    return { ...item, material_check_status: props.latestCheck.status }
  }
  return item.is_current && props.latestSubmission?.version > item.version
    ? { ...item, is_current: false } : item
}))
const statusName = (status) => ({
  PENDING: '检查中', VALID: '完整性检查通过', INVALID: '材料不完整', RETURNED: '已退回',
}[status] || '暂无检查记录')
const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN') : '未记录'

async function refresh(resetPage = false, targetPage = page.value) {
  const request = ++historyRequest
  loading.value = true
  error.value = ''
  try {
    const data = await getProjectSubmissionHistory(props.assignmentId, resetPage ? 1 : targetPage, pageSize)
    if (request !== historyRequest) return
    items.value = data.items
    total.value = data.total
    page.value = data.page
  } catch (err) {
    if (request === historyRequest) error.value = err.message
  } finally {
    if (request === historyRequest) loading.value = false
  }
}

async function selectResult(item = selected.value) {
  const request = ++detailRequest
  selected.value = item
  selectedCheck.value = null
  detailLoading.value = true
  detailError.value = ''
  try {
    const result = await getMaterialCheck(item.id)
    if (request === detailRequest) selectedCheck.value = result
  } catch (err) {
    if (request === detailRequest) detailError.value = err.message
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
}

onMounted(() => refresh())
watch(() => props.latestSubmission?.id, (id, previous) => {
  if (id && id !== previous) void refresh(true)
})
onBeforeUnmount(() => { historyRequest++; detailRequest++ })
</script>

<template>
  <section class="project-history" aria-labelledby="project-history-title">
    <header class="history-heading">
      <div><h2 id="project-history-title">期末提交历史</h2><p>查看本人各版本的材料检查结果，历史记录只读。</p></div>
      <button type="button" :disabled="loading" @click="refresh()">{{ loading ? '正在刷新…' : '刷新提交历史' }}</button>
    </header>
    <p v-if="error" class="history-error" role="alert">历史加载失败：{{ error }}</p>
    <p v-if="loading" role="status">正在加载提交历史…</p>
    <p v-else-if="!error && total === 0">暂无提交记录。</p>
    <template v-if="rows.length">
      <div class="history-table-wrap">
        <table>
          <caption>共 {{ total }} 次提交 · 最新版本在前</caption>
          <thead><tr><th>版本</th><th>提交时间</th><th>材料检查</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="item in rows" :key="item.id" :class="{ selected: selected?.id === item.id }">
              <td>第 {{ item.version }} 版<span v-if="item.is_current" class="current-tag">当前版本</span></td>
              <td>{{ formatTime(item.submitted_at) }}</td>
              <td>{{ statusName(item.material_check_status) }}</td>
              <td><button type="button" :aria-pressed="selected?.id === item.id" :aria-label="`查看第 ${item.version} 版材料检查`" @click="selectResult(item)">查看检查结果</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav class="history-pagination" aria-label="期末提交历史分页">
        <button type="button" :disabled="loading || page <= 1" @click="refresh(false, page - 1)">上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <button type="button" :disabled="loading || page >= pageCount" @click="refresh(false, page + 1)">下一页</button>
      </nav>
    </template>
    <section v-if="selected" class="history-detail" aria-label="历史材料检查详情">
      <div class="history-heading">
        <h3>第 {{ selected.version }} 版材料检查</h3>
        <button type="button" :disabled="detailLoading" @click="selectResult()">刷新此版本结果</button>
      </div>
      <p>查看历史不会替换上方当前版本，也不会改变上传表单。</p>
      <p v-if="detailLoading" role="status">正在读取检查结果…</p>
      <p v-else-if="detailError" class="history-error" role="alert">{{ detailError }}，请刷新此版本结果重试。</p>
      <template v-else-if="selectedCheck">
        <p>材料检查：{{ statusName(selectedCheck.status) }}</p>
        <p v-if="selectedCheck.status === 'PENDING'">此版本仍在后台检查，可手动刷新读取结果。</p>
        <p v-if="selectedCheck.checked_at">检查时间：{{ formatTime(selectedCheck.checked_at) }}</p>
        <p v-if="selectedCheck.missing_items.length">缺失项：{{ selectedCheck.missing_items.join('、') }}</p>
        <p v-if="selectedCheck.warnings.length">提示：{{ selectedCheck.warnings.join('、') }}</p>
      </template>
    </section>
  </section>
</template>

<style scoped src="./submission-history.css"></style>
