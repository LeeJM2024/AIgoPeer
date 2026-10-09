<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  getAssignment,
  getClassStudents,
  initializeReviewTasks,
  publishAssignment,
  savePanels,
  getAlgorithmRuns,
  aggregateReviews,
  getProgrammingResults,
} from '../../api/teacher'

const route = useRoute()
const assignment = ref(null)
const students = ref({})
const selections = ref({})
const error = ref('')
const notice = ref('')
const busy = ref('')
const id = Number(route.params.id)
const runs = ref([])
const programmingResults = ref([])
const judgeNames = {
  QUEUED: '排队中',
  RUNNING: '测评中',
  AC: '通过',
  WA: '答案错误',
  TLE: '超时',
  RE: '运行错误',
  CE: '编译错误',
  SYSTEM_ERROR: '判题服务故障',
}
const stateName = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
  SUBMITTING: '提交中',
  REVIEWER_INITIALIZING: '任务初始化',
  REVIEWER_GRADING: '跨班评审中',
  AGGREGATING: '评分聚合中',
  TEACHER_GRADING: '教师评分中',
  PUBLISHED_RESULT: '成绩已发布',
}
const canEditPanels = computed(() => assignment.value?.status === 'DRAFT')
async function load() {
  error.value = ''
  try {
    assignment.value = await getAssignment(id)
    runs.value = await getAlgorithmRuns(id)
    if (assignment.value.type === 'PROGRAMMING')
      programmingResults.value = await getProgrammingResults(id)
    const entries = await Promise.all(
      assignment.value.classes.map(async (c) => [
        c.id,
        await getClassStudents(c.id),
      ]),
    )
    students.value = Object.fromEntries(entries)
    selections.value = Object.fromEntries(
      assignment.value.classes.map((c) => {
        const panel = assignment.value.panels.find(
          (p) => p.reviewer_class_id === c.id,
        )
        return [c.id, panel?.reviewer_ids || []]
      }),
    )
  } catch (err) {
    error.value = err.message
  }
}
onMounted(load)
function panelForReviewerClass(reviewerClass) {
  return {
    target_class_id: assignment.value.classes.find(
      (c) => c.id !== reviewerClass.id,
    ).id,
    reviewer_class_id: reviewerClass.id,
    reviewer_ids: selections.value[reviewerClass.id] || [],
  }
}
async function run(action, label) {
  error.value = ''
  notice.value = ''
  busy.value = label
  try {
    const result = await action()
    notice.value =
      label === 'panels'
        ? '两组评审人已保存。'
        : label === 'publish'
          ? '作业已发布。'
          : label === 'aggregate'
            ? result.panels.every((p) => p.status === 'NO_VALID_SUBMISSIONS')
              ? '暂无当前有效提交，尚未进入教师评分阶段。'
              : result.panels.every((p) =>
                ['COMPLETED', 'NO_VALID_SUBMISSIONS'].includes(p.status),
              )
              ? '评分聚合已完成。请进入评分工作台。'
              : '部分评审组尚未完成聚合，请查看下方运行记录；缺失评分需要先补齐。'
            : `评审任务已生成，共 ${result.panels.reduce((n, p) => n + p.task_count, 0)} 条。`
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div v-if="assignment" class="view-stack">
    <nav class="breadcrumbs" aria-label="面包屑">
      <RouterLink to="/teacher/assignments">作业与评分</RouterLink><span>/</span
      ><span>{{ assignment.title }}</span>
    </nav>
    <header class="page-heading">
      <div>
        <span class="status-chip">{{
          stateName[assignment.status] || assignment.status
        }}</span>
        <h1>{{ assignment.title }}</h1>
        <p v-if="assignment.type === 'FINAL_PROJECT'">
          {{ assignment.classes.map((c) => c.name).join(' · ') }} · 教师
          {{ Number(assignment.teacher_weight) * 100 }}% / 跨班评审
          {{ Number(assignment.designated_review_weight) * 100 }}%
        </p>
        <p v-else>
          {{ assignment.classes.map((c) => c.name).join(' · ') }} · C++17
          自动测评
        </p>
      </div>
      <RouterLink
        v-if="assignment.type === 'FINAL_PROJECT'"
        class="button button-secondary"
        :to="`/teacher/assignments/${id}/grading`"
        >进入评分工作台</RouterLink
      >
    </header>
    <nav
      v-if="assignment.type === 'FINAL_PROJECT'"
      class="toolbar"
      aria-label="作业工作区"
    >
      <RouterLink
        class="button button-secondary"
        :to="`/teacher/assignments/${id}/reviews`"
        >评审与异常复核</RouterLink
      ><RouterLink
        class="button button-secondary"
        :to="`/teacher/assignments/${id}/statistics`"
        >成绩统计与导出</RouterLink
      ><RouterLink
        v-if="assignment.status === 'DRAFT'"
        class="button button-secondary"
        to="/teacher/assignments"
        >返回列表编辑草稿</RouterLink
      >
    </nav>
    <p v-if="error" class="notice notice-error" role="alert">
      操作未完成：{{ error }}
    </p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <section
      v-if="assignment.type === 'PROGRAMMING' && assignment.programming_problem"
      class="data-section"
    >
      <h2>题目说明</h2>
      <p class="preserve-lines">
        {{ assignment.programming_problem.statement }}
      </p>
      <h3>输入说明</h3>
      <p class="preserve-lines">
        {{ assignment.programming_problem.input_description }}
      </p>
      <h3>输出说明</h3>
      <p class="preserve-lines">
        {{ assignment.programming_problem.output_description }}
      </p>
      <p>
        时限 {{ assignment.programming_problem.time_limit_ms }} ms · 内存
        {{ assignment.programming_problem.memory_limit_mb }} MB
      </p>
      <details
        v-for="(item, index) in assignment.programming_problem.test_cases"
        :key="index"
      >
        <summary>
          用例 {{ index + 1 }} ·
          {{ item.is_public ? '公开样例' : '隐藏用例（仅教师可见）' }}
        </summary>
        <div class="form-grid">
          <div>
            <strong>输入</strong>
            <pre>{{ item.input_data }}</pre>
          </div>
          <div>
            <strong>预期输出</strong>
            <pre>{{ item.expected_output }}</pre>
          </div>
        </div>
      </details>
      <RouterLink v-if="assignment.status === 'DRAFT'" to="/teacher/assignments"
        >返回作业列表编辑题目</RouterLink
      >
      <p v-else class="muted">
        题目与测试用例已冻结。如需修改，请创建新作业，以保留原有测评依据。
      </p>
    </section>
    <section v-if="assignment.type === 'PROGRAMMING'" class="data-section">
      <div class="section-heading">
        <h2>学生提交与测评结果</h2>
        <button
          class="button button-secondary button-small"
          :disabled="busy"
          @click="load"
        >
          刷新
        </button>
      </div>
      <p>
        {{ programmingResults.length }} 人已提交 ·
        {{
          programmingResults.filter((r) => r.status === 'AC').length
        }}
        人通过。服务故障不计为学生错误。
      </p>
      <div v-if="programmingResults.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>学生</th>
              <th>班级</th>
              <th>版本</th>
              <th>状态</th>
              <th>已通过 / 已执行用例</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in programmingResults" :key="row.id">
              <td>
                {{ row.name }}<small>{{ row.student_no }}</small>
              </td>
              <td>{{ row.class_name }}</td>
              <td>v{{ row.version }}</td>
              <td>{{ judgeNames[row.status] || row.status }}</td>
              <td>
                {{ row.passed_case_count }} / {{ row.executed_case_count }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty-state compact">
        尚无代码提交。发布后学生可从“我的作业”进入提交。
      </p>
    </section>
    <section v-if="assignment.type === 'FINAL_PROJECT'" class="data-section">
      <div class="section-heading">
        <div>
          <h2>评分量表</h2>
          <p>教师端和评审端都使用同一份 Rubric。</p>
        </div>
        <strong
          >{{
            assignment.rubric_items.reduce(
              (n, item) => n + Number(item.max_score),
              0,
            )
          }}
          分</strong
        >
      </div>
      <ol class="rubric-list">
        <li v-for="item in assignment.rubric_items" :key="item.id">
          <span>{{ item.sort_order }}</span>
          <div>
            <strong>{{ item.name }}</strong>
            <p>{{ item.description || '暂无评分说明' }}</p>
          </div>
          <b>{{ item.max_score }} 分</b>
        </li>
      </ol>
    </section>
    <section v-if="assignment.type === 'FINAL_PROJECT'" class="data-section">
      <div class="section-heading">
        <div>
          <h2>固定跨班五人评审组</h2>
          <p>每组五人将评阅对方班全部材料合格的作业。</p>
        </div>
      </div>
      <div class="panel-grid">
        <fieldset
          v-for="classItem in assignment.classes"
          :key="classItem.id"
          :disabled="!canEditPanels || Boolean(busy)"
        >
          <legend>{{ classItem.name }}评审组</legend>
          <p>
            评阅：{{
              assignment.classes.find((c) => c.id !== classItem.id).name
            }}
          </p>
          <label
            v-for="student in students[classItem.id]"
            :key="student.id"
            class="check-row"
            ><input
              v-model="selections[classItem.id]"
              type="checkbox"
              :value="student.id"
              :disabled="
                canEditPanels &&
                selections[classItem.id]?.length >= 5 &&
                !selections[classItem.id]?.includes(student.id)
              "
            /><span
              >{{ student.name }} <small>{{ student.student_no }}</small></span
            ></label
          >
          <div
            class="selection-count"
            :class="{ complete: selections[classItem.id]?.length === 5 }"
          >
            已选择 {{ selections[classItem.id]?.length || 0 }} / 5 人
          </div>
        </fieldset>
      </div>
      <div v-if="canEditPanels" class="form-actions">
        <button
          class="button"
          :disabled="
            busy ||
            assignment.classes.some((c) => selections[c.id]?.length !== 5)
          "
          @click="
            run(
              () =>
                savePanels(id, assignment.classes.map(panelForReviewerClass)),
              'panels',
            )
          "
        >
          保存评审组
        </button>
      </div>
    </section>
    <section class="action-bar">
      <div>
        <h2>流程控制</h2>
        <p v-if="assignment.status === 'DRAFT'">
          {{
            assignment.type === 'PROGRAMMING'
              ? '确认题目和公开、隐藏用例后发布，无需配置跨班评审组。'
              : '确认 Rubric 和两个评审组后发布。'
          }}发布后规则将被冻结。
        </p>
        <p v-else-if="assignment.status === 'PUBLISHED'">
          {{
            assignment.type === 'PROGRAMMING'
              ? '学生可以提交 C++17 代码，由判题服务执行自动测评。'
              : '提交截止后可根据当前有效作业生成评审任务。'
          }}
        </p>
        <p v-else>
          当前状态：{{ assignment.status }}。任务和成绩记录会保留审计痕迹。
        </p>
      </div>
      <button
        v-if="assignment.status === 'DRAFT'"
        class="button"
        :disabled="
          busy ||
          (assignment.type === 'FINAL_PROJECT' &&
            assignment.panels.length !== 2)
        "
        @click="run(() => publishAssignment(id), 'publish')"
      >
        确认并发布作业</button
      ><button
        v-else-if="
          assignment.type === 'FINAL_PROJECT' &&
          ['PUBLISHED', 'SUBMITTING', 'REVIEWER_INITIALIZING'].includes(
            assignment.status,
          )
        "
        class="button"
        :disabled="busy"
        @click="run(() => initializeReviewTasks(id), 'initialize')"
      >
        初始化跨班评审任务
      </button>
      <button
        v-if="
          assignment.type === 'FINAL_PROJECT' &&
          ['REVIEWER_GRADING', 'AGGREGATING', 'TEACHER_GRADING'].includes(
            assignment.status,
          )
        "
        class="button"
        :disabled="busy"
        @click="run(() => aggregateReviews(id), 'aggregate')"
      >
        {{ busy === 'aggregate' ? '正在聚合…' : '生成或重试评审聚合' }}
      </button>
    </section>
    <section
      v-if="assignment.type === 'FINAL_PROJECT' && runs.length"
      class="data-section"
    >
      <h2>最近运行记录</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>运行</th>
              <th>评审组</th>
              <th>类型</th>
              <th>状态</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="runItem in runs" :key="runItem.id">
              <td>#{{ runItem.id }}</td>
              <td>{{ runItem.panel_id }}</td>
              <td>
                {{
                  runItem.algorithm_name === 'panel_bayesian_robust'
                    ? '评分聚合'
                    : '任务初始化'
                }}
              </td>
              <td>
                {{
                  { COMPLETED: '已完成', FAILED: '失败', RUNNING: '处理中' }[
                    runItem.status
                  ] || runItem.status
                }}
              </td>
              <td>
                {{
                  runItem.parameters_json?.failure_reason ===
                  'INSUFFICIENT_REVIEWS'
                    ? '五人评分未齐，请补齐后重试'
                    : runItem.status === 'FAILED'
                      ? '请联系维护人员检查本次运行后重试'
                      : '—'
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
  <div v-else class="view-stack">
    <p v-if="error" class="notice notice-error">加载失败：{{ error }}</p>
    <div v-else class="skeleton-page" />
  </div>
</template>
<style scoped>
.preserve-lines {
  white-space: pre-wrap;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
details {
  padding: 12px 0;
}
</style>
