<script setup>
import { computed } from 'vue'

const props = defineProps({
  evidence: { type: Object, default: () => ({}) },
  rubricItems: { type: Array, default: () => [] },
})
const reasons = {
  REPEATED_SIGNED_RELATIONSHIP: '多轮作业中，该评委持续对同一作者异常抬分或压分。',
  PERSISTENT_POSITIVE_CYCLE: '历史评分中出现持续异常抬分的关系环。',
  CONCENTRATED_RELATIONSHIP_RESIDUALS: '重复配对同时出现集中异常残差，需要核对评分关系。',
  FOUR_VS_ONE_OUTLIER: '这位评审人的评分与其他四人相差较大。',
  POSTERIOR_OUTLIER: '这次评分偏离了其他评审记录，需要核对。',
  MODEL_MEDIAN_CONFLICT: '不同计算方式给出的参考分差距较大。',
  WIDE_CREDIBLE_INTERVAL: '当前参考分不够稳定，请结合材料判断。',
  LOW_SCORE_DIVERSITY: '各评分项的得分比例过于接近，建议核对评分依据。',
}
const data = computed(() => props.evidence || {})
const rules = computed(() => Array.isArray(data.value.rules_triggered) ? data.value.rules_triggered.filter((rule) => !['SHORT_DURATION', 'SHORT_COMMENT'].includes(rule)) : [])
const rows = computed(() => Array.isArray(data.value.rubric_evidence) ? data.value.rubric_evidence : [])
function score(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number) ? String(Math.round(number * 100) / 100) : '—'
}
function rubricName(item, index) {
  return props.rubricItems.find((r) => String(r.id) === String(item.rubric_item_id))?.name || `评分项 ${index + 1}`
}
</script>

<template>
  <div class="review-explanation">
    <ul v-if="rules.length" class="evidence-reasons">
      <li v-for="(rule, index) in rules" :key="index">{{ reasons[rule] || '这次评分需要核对，请结合材料、分数和评语复核。' }}</li>
    </ul>
    <p v-else>{{ typeof data.reason === 'string' ? data.reason : '请结合学生材料和五位评审人的评分、评语进行复核。' }}</p>
    <p v-if="data.uncertainty_evidence?.fallback_reason === 'PANEL_TOO_SMALL'" class="muted">可比较的作业较少，本次参考分采用五人评分的中间值。</p>
    <p v-else-if="data.uncertainty_evidence?.fallback_reason === 'MODEL_NOT_CONVERGED'" class="muted">本次计算未得到稳定结果，参考分采用五人评分的中间值。</p>
    <div v-if="rows.length" class="table-wrap">
      <table>
        <thead><tr><th>评分项</th><th>本次评分</th><th>其余四人中间分</th><th>满分</th></tr></thead>
        <tbody><tr v-for="(item, index) in rows" :key="index"><td>{{ rubricName(item, index) }}</td><td>{{ score(item.reviewer_score) }}</td><td>{{ score(item.other_four_median) }}</td><td>{{ score(item.max_score) }}</td></tr></tbody>
      </table>
    </div>
    <p v-if="data.behavior_evidence" class="muted evidence-behavior">
      评阅用时：{{ score(data.behavior_evidence.duration_seconds) }} 秒 · 评语：{{ score(data.behavior_evidence.comment_char_count) }} 字
    </p>
    <details v-if="data.relationship_evidence" class="evidence-more">
      <summary>历史关系证据与任务溯源</summary>
      <p>配对覆盖 {{ data.relationship_evidence.pair_assignment_count }} 轮，其中同向异常 {{ data.relationship_evidence.signed_assignment_count }} 轮。</p>
      <p v-if="data.relationship_evidence.cycle">关系环（账号 ID）：{{ data.relationship_evidence.cycle.join(' → ') }}</p>
      <ul><li v-for="sample in data.relationship_evidence.support" :key="`${sample.assignment_id}-${sample.task_id}`">作业 #{{ sample.assignment_id }} · 任务 #{{ sample.task_id }} · 标准化残差 {{ score(sample.residual) }} · 算法运行 #{{ sample.algorithm_run_id ?? '本次' }}</li></ul>
    </details>
    <details v-if="rows.length" class="evidence-more">
      <summary>更多分数对照</summary>
      <dl v-for="(item, index) in rows" :key="index">
        <dt>{{ rubricName(item, index) }}</dt>
        <dd>其他四人最高分与最低分之差：{{ score(item.other_four_span) }}</dd>
        <dd>五人评分中间值：{{ score(item.median_score) }}</dd>
        <dd v-if="data.uncertainty_evidence?.posterior_available === true">模型参考分：{{ score(item.bayesian_score) }} · 参考范围：{{ score(item.ci_lower) }} 至 {{ score(item.ci_upper) }}</dd>
        <dd v-if="item.ci_risk_threshold">区间过宽判定线：满分的 {{ score(item.ci_risk_threshold * 100) }}%{{ item.ci_risk_threshold > 0.2 ? '（该作品评委样本不足，画像均使用先验）' : '' }}</dd>
      </dl>
    </details>
  </div>
</template>

<style scoped>
.review-explanation { margin:14px 0; line-height:1.7; }
.evidence-reasons { padding-left:20px; }
.evidence-reasons li + li { margin-top:6px; }
.evidence-behavior { margin-top:12px; }
.evidence-more { font-size:13px; margin-top:14px; }
.evidence-more summary { cursor:pointer; }
dt { font-weight:600; }
dd { margin:4px 0; color:var(--muted); }
</style>
