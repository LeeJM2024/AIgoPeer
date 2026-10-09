<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getStatistics } from '../../api/teacher'
const id = Number(useRoute().params.id),
  data = ref(null),
  error = ref('')
onMounted(async () => {
  try {
    data.value = await getStatistics(id)
  } catch (err) {
    error.value = err.message
  }
})
function exportCsv() {
  const headers = [
    '学号',
    '姓名',
    '班级',
    '提交编号',
    '教师分',
    '评审分',
    '最终分',
    '成绩来源',
    '复核最终分',
    '复核理由',
    '教师分版本',
    '教师权重',
    '评审权重',
    '发布时间',
  ]
  const rows = data.value.grades.map((g) => [
    g.student_no,
    g.name,
    g.class_name,
    g.submission_id,
    g.teacher_score,
    g.aggregate_score,
    g.final_score,
    g.final_grade_source === 'TEACHER_FINAL_REVIEW'
      ? '教师复核最终分'
      : '教师与评审加权',
    g.final_review_score,
    g.final_review_reason,
    g.teacher_grade_version,
    g.teacher_weight,
    g.designated_review_weight,
    g.published_at,
  ])
  const escape = (value) => {
    let s = String(value ?? '')
    if (/^[\s]*[=+\-@]/.test(s)) s = "'" + s
    return '"' + s.replaceAll('"', '""') + '"'
  }
  const csv =
    '\uFEFF' +
    [headers, ...rows].map((row) => row.map(escape).join(',')).join('\r\n')
  const url = URL.createObjectURL(
    new Blob([csv], { type: 'text/csv;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `作业-${id}-已发布成绩.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<template>
  <div class="view-stack">
    <nav class="breadcrumbs">
      <RouterLink :to="`/teacher/assignments/${id}`">作业详情</RouterLink
      ><span>/</span><span>成绩统计</span>
    </nav>
    <header class="page-heading">
      <div>
        <h1>成绩统计</h1>
        <p>
          {{ data?.assignment.title }} ·
          分数与统计均来自服务器保存的已发布结果。
        </p>
      </div>
      <button
        class="button"
        :disabled="!data?.grades.length"
        @click="exportCsv"
      >
        导出已发布成绩
      </button>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="!data && !error" class="skeleton-page" />
    <template v-if="data"
      ><section class="data-section">
        <h2>提交与评审</h2>
        <dl class="report-facts">
          <div>
            <dt>提交记录 / 有效记录</dt>
            <dd>{{ data.submissions.total }} / {{ data.submissions.valid }}</dd>
          </div>
          <div>
            <dt>已完成 / 总评审任务</dt>
            <dd>{{ data.reviews.completed }} / {{ data.reviews.total }}</dd>
          </div>
          <div>
            <dt>已发布成绩</dt>
            <dd>{{ data.published_count }} 份</dd>
          </div>
          <div>
            <dt>平均分 / 满分</dt>
            <dd>{{ data.average ?? '—' }} / {{ data.maximum_score }}</dd>
          </div>
          <div>
            <dt>及格率（满分的60%）</dt>
            <dd>
              {{
                data.pass_rate === null
                  ? '—'
                  : (Number(data.pass_rate) * 100).toFixed(1) + '%'
              }}
            </dd>
          </div>
        </dl>
      </section>
      <section class="data-section">
        <h2>成绩分布</h2>
        <p class="muted">按量表满分的比例分段，支持非100分量表。</p>
        <div
          v-for="bin in data.distribution"
          :key="bin.label"
          class="distribution-row"
        >
          <span>{{ bin.label }}</span
          ><meter
            min="0"
            :max="Math.max(data.published_count, 1)"
            :value="bin.count"
            :aria-label="bin.label"
          /><b>{{ bin.count }} 份</b>
        </div>
        <p v-if="!data.published_count" class="empty-state compact">
          成绩尚未发布，暂无分布数据。
        </p>
      </section>
      <section class="data-section">
        <h2>已发布成绩明细</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>学号 / 姓名</th>
                <th>班级</th>
                <th>教师分</th>
                <th>聚合分</th>
                <th>最终分</th>
                <th>采用版本</th>
                <th>成绩来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in data.grades" :key="g.submission_id">
                <td>
                  {{ g.student_no }}<small>{{ g.name }}</small>
                </td>
                <td>{{ g.class_name }}</td>
                <td>{{ g.teacher_score }}</td>
                <td>{{ g.aggregate_score }}</td>
                <td>
                  <strong>{{ g.final_score }}</strong>
                </td>
                <td>v{{ g.teacher_grade_version }}</td>
                <td>
                  {{
                    g.final_grade_source === 'TEACHER_FINAL_REVIEW'
                      ? '教师复核最终分'
                      : '按权重加权'
                  }}<small v-if="g.final_review_reason">{{
                    g.final_review_reason
                  }}</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>
