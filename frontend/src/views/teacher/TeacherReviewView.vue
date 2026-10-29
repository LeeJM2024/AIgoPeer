<script setup>
import { onMounted, reactive, ref } from 'vue'
import ReviewEvidence from '../../components/teacher/ReviewEvidence.vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  extendReviewDeadline,
  getAnomalies,
  getAssignment,
  getReviewProgress,
  resolveAnomaly,
  replaceReviewTask,
} from '../../api/teacher'

const id = Number(useRoute().params.id),
  assignment = ref(null),
  anomalies = ref([]),
  progress = ref([])
const error = ref(''),
  notice = ref(''),
  busy = ref(false),
  notes = reactive({}),
  deadline = ref(''),
  reason = ref('')
const replacement = ref(null), replacementReason = ref('')
async function replace() {
  if (!replacement.value || busy.value) return
  busy.value = true
  error.value = ''; notice.value = ''
  try {
    await replaceReviewTask(id, replacement.value.task_id, replacementReason.value)
    replacement.value = null; replacementReason.value = ''
    await load()
    notice.value = '替补任务已生成，原任务已停用并留档。'
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
const statusNames = {
  OPEN: '待复核',
  CONFIRMED: '确认异常',
  DISMISSED: '已驳回',
}
async function load() {
  ;[assignment.value, anomalies.value, progress.value] = await Promise.all([
    getAssignment(id),
    getAnomalies(id),
    getReviewProgress(id),
  ])
}
onMounted(async () => {
  try {
    await load()
  } catch (err) {
    error.value = err.message
  }
})
async function resolve(item, status) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await resolveAnomaly(item.id, { status, note: notes[item.id] || '' })
    await load()
    notice.value = '复核结论已记录，原始分数保持不变。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function extend() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await extendReviewDeadline(id, {
      review_deadline: new Date(deadline.value).toISOString(),
      reason: reason.value,
    })
    await load()
    deadline.value = ''
    reason.value = ''
    notice.value = '评审截止时间已延长。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="view-stack">
    <nav class="breadcrumbs">
      <RouterLink :to="`/teacher/assignments/${id}`">作业详情</RouterLink
      ><span>/</span><span>评审与异常复核</span>
    </nav>
    <header class="page-heading">
      <div>
        <h1>评审与异常复核</h1>
        <p>
          {{ assignment?.title }}
        </p>
      </div>
      <RouterLink
        class="button button-secondary"
        :to="`/teacher/assignments/${id}/grading`"
        >返回评分</RouterLink
      >
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <div v-if="!assignment && !error" class="skeleton-page" />
    <template v-if="assignment">
      <section class="data-section">
        <h2>跨班评审完成情况</h2>
        <p>每份作品收齐 5 份有效评分后才能正式汇总。替补仅针对尚未提交的任务。</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>目标班</th>
                <th>评审人</th>
                <th>完成情况</th>
                <th>未完成任务</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in progress"
                :key="`${row.panel_id}-${row.reviewer_id}`"
              >
                <td>{{ row.target_class_name }}</td>
                <td>
                  {{ row.reviewer_name }}<small>{{ row.student_no }}</small>
                </td>
                <td>{{ row.completed_count }} / {{ row.task_count }}</td>
                <td>
                  <details v-if="row.missing_tasks.length">
                    <summary>{{ row.missing_tasks.length }} 条待完成</summary>
                    <ul>
                      <li v-for="task in row.missing_tasks" :key="task.task_id">
                        {{ task.anonymous_token }} ·
                        {{ task.status === 'PENDING' ? '未开始' : '未提交' }}
                        <button v-if="assignment.status === 'REVIEWER_GRADING' && new Date(assignment.review_deadline) > new Date()"
                          class="button button-secondary button-small" :disabled="busy"
                          @click="replacement = task; replacementReason = ''">安排替补</button>
                      </li>
                    </ul>
                  </details>
                  <span v-else>{{
                    row.task_count ? '全部完成' : '尚未分配任务'
                  }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!progress.length" class="empty-state compact">
          尚未生成跨班评审任务。
        </p>
      </section>
      <form v-if="replacement" class="data-section" aria-labelledby="replacement-heading" @submit.prevent="replace">
        <h2 id="replacement-heading">确认替补 · {{ replacement.anonymous_token }}</h2>
        <p>系统会从对方班的参与学生中选择符合关系约束、当前负担较低的人选。确认后原任务停止接受评分。</p>
        <label>替补原因<textarea v-model="replacementReason" required minlength="3" maxlength="1000" :disabled="busy" /></label>
        <div class="form-actions"><button class="button" :disabled="busy || replacementReason.trim().length < 3">{{ busy ? '正在安排…' : '确认并安排替补' }}</button>
          <button type="button" class="button button-secondary" :disabled="busy" @click="replacement = null">取消</button></div>
      </form>
      <form
        v-if="
          ['PUBLISHED', 'SUBMITTING', 'REVIEWER_GRADING'].includes(
            assignment.status,
          )
        "
        class="data-section"
        @submit.prevent="extend"
      >
        <h2>延长评审截止时间</h2>
        <p class="muted">
          当前截止：{{
            assignment.review_deadline
              ? new Date(assignment.review_deadline).toLocaleString()
              : '未设置'
          }}
        </p>
        <fieldset class="form-grid bare-fieldset" :disabled="busy">
          <label
            >新的评审截止时间<input
              v-model="deadline"
              type="datetime-local"
              required /></label
          ><label
            >延期原因<input
              v-model="reason"
              required
              minlength="3"
              maxlength="1000"
          /></label>
        </fieldset>
        <div class="form-actions">
          <button class="button" :disabled="busy">保存延期</button>
        </div>
      </form>
      <section class="data-section">
        <div class="section-heading">
          <h2>需要复核的评分</h2>
          <span
            >{{
              anomalies.filter((a) => a.status === 'OPEN').length
            }}
            条待复核</span
          >
        </div>
        <p v-if="!anomalies.length" class="empty-state compact">
          暂无需要复核的评分。
        </p>
        <article v-for="item in anomalies" :key="item.id" class="anomaly-row">
          <div class="section-heading">
            <div>
              <h3>{{ item.author_name }} · {{ item.student_no }}</h3>
              <p>
                匿名编号 {{ item.anonymous_token }} ·
                {{ { HIGH: '高风险', MEDIUM: '中风险', LOW: '低风险' }[item.risk_level] || '待核对' }}
              </p>
            </div>
            <span class="status-chip">{{ statusNames[item.status] }}</span>
          </div>
          <details>
            <summary>查看复核依据</summary>
            <ReviewEvidence :evidence="item.evidence_json" :rubric-items="assignment.rubric_items" />
          </details>
          <template
            v-if="
              item.status === 'OPEN' &&
              item.risk_level !== 'HIGH' &&
              assignment.status !== 'PUBLISHED_RESULT'
            "
            ><label
              >复核说明（选填）<textarea
                v-model="notes[item.id]"
                rows="2"
                maxlength="2000"
                :disabled="busy"
              />
            </label>
            <div class="form-actions">
              <button
                class="button button-secondary"
                :disabled="busy"
                @click="resolve(item, 'DISMISSED')"
              >
                驳回异常</button
              ><button
                class="button"
                :disabled="busy"
                @click="resolve(item, 'CONFIRMED')"
              >
                确认异常
              </button>
            </div></template
          ><p
            v-else-if="item.status === 'OPEN' && item.risk_level === 'HIGH'"
            class="notice notice-error"
          >
            高风险异常须在评分工作台录入复核最终分，不能在此确认或驳回。
          </p>
          <p v-else class="review-conclusion">
            {{ item.resolution_note || '未填写复核说明'
            }}<small v-if="item.resolved_at">
              · {{ new Date(item.resolved_at).toLocaleString() }}</small
            >
          </p>
        </article>
      </section>
    </template>
  </div>
</template>
