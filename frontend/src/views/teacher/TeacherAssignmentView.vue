<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ProgrammingHistory from '../../components/teacher/ProgrammingHistory.vue'
import SubjectiveAnswers from '../../components/teacher/SubjectiveAnswers.vue'
import { subjectiveTypes } from '../../presentation/assignments'
import {
  getAssignment,
  getClassStudents,
  initializeReviewTasks,
  publishAssignment,
  getAllocationPreview,
  getAlgorithmRuns,
  aggregateReviews,
  getProgrammingResults,
  closeAssignment,
  reopenAssignment,
  deleteAssignment,
  finishSubmissions,
} from '../../api/teacher'

const route = useRoute()
const router = useRouter()
const assignment = ref(null)
const isSubjective = computed(() => subjectiveTypes.includes(assignment.value?.type))
const students = ref({})
const allocation = ref(null)
const confirmedSnapshot = ref('')
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
  REVIEWER_INITIALIZING: '分配评审',
  REVIEWER_GRADING: '跨班评审中',
  AGGREGATING: '汇总评审中',
  TEACHER_GRADING: '教师评分中',
  PUBLISHED_RESULT: '成绩已发布',
}
const intakeOpen = computed(() => assignment.value && !assignment.value.closed_at && !assignment.value.submissions_closed_at && ['PUBLISHED', 'SUBMITTING', 'REVIEWER_GRADING'].includes(assignment.value.status) && new Date(assignment.value.submit_deadline) > new Date())
const canInitialize = computed(() => !assignment.value?.closed_at && allocation.value?.ready && (allocation.value.new_task_count ?? 1) > 0 && confirmedSnapshot.value === allocation.value.snapshot_hash && new Date(assignment.value.review_deadline) > new Date())
async function load() {
  error.value = ''
  try {
    assignment.value = await getAssignment(id)
    runs.value = assignment.value.type === 'FINAL_PROJECT' ? await getAlgorithmRuns(id) : []
    if (assignment.value.type === 'PROGRAMMING')
      programmingResults.value = await getProgrammingResults(id)
    const entries = await Promise.all(
      assignment.value.classes.map(async (c) => [
        c.id,
        await getClassStudents(c.id),
      ]),
    )
    students.value = Object.fromEntries(entries)
    if (assignment.value.type === 'FINAL_PROJECT' && !assignment.value.closed_at) await refreshPreview()
  } catch (err) {
    error.value = err.message
  }
}
onMounted(load)
async function refreshPreview() {
  confirmedSnapshot.value = ''
  allocation.value = null
  try {
    allocation.value = await getAllocationPreview(id)
  } catch (err) { error.value = err.message }
}
async function initialize() {
  if (!canInitialize.value || busy.value) return
  const hash = allocation.value.snapshot_hash
  await run(() => initializeReviewTasks(id, hash), 'initialize')
}
async function toggleClosed() {
  if (!confirm(assignment.value.closed_at ? '恢复此作业？按原有阶段与截止时间继续。' : '关闭此作业？学生提交和评审将暂停，可稍后恢复。')) return
  await run(() => assignment.value.closed_at ? reopenAssignment(id) : closeAssignment(id), assignment.value.closed_at ? 'reopen' : 'close')
}
async function removeAssignment() {
  if (!confirm(`删除作业“${assignment.value.title}”？删除后将从教师与学生入口移除，现有链接不可继续访问。`)) return
  busy.value = 'delete'; error.value = ''
  try { await deleteAssignment(id); await router.push('/teacher/assignments') }
  catch (err) { error.value = err.message }
  finally { busy.value = '' }
}
async function finishIntake() {
  if (!confirm(isSubjective.value ? '结束提交？将停止接收新答案和新版本，已提交答案仍可查看。' : '结束提交？将停止接收新作品和新版本，已有评审任务继续进行。')) return
  await run(() => finishSubmissions(id), 'finish')
}
async function run(action, label) {
  error.value = ''
  notice.value = ''
  busy.value = label
  try {
    const result = await action()
    notice.value = ({ close: '作业已关闭，可恢复后继续。', reopen: '作业已恢复。', finish: isSubjective.value ? '已结束提交，可查看学生答案与历史版本。' : '已结束提交。请补充分配新增作品，再汇总评审。' })[label] ||
    (
      label === 'publish'
          ? '作业已发布。'
          : label === 'aggregate'
            ? result.panels.every((p) => p.status === 'NO_VALID_SUBMISSIONS')
              ? '暂无当前有效提交，尚未进入教师评分阶段。'
              : result.panels.every((p) =>
                ['COMPLETED', 'NO_VALID_SUBMISSIONS'].includes(p.status),
              )
              ? '评审结果汇总完成。请进入评分工作台。'
              : '部分评审结果尚未汇总，请先补齐评分，再重新汇总。'
            : `评审任务已生成，共 ${result.panels.reduce((n, p) => n + p.task_count, 0)} 条。`)
    await load()
  } catch (err) {
    if (label === 'initialize') { confirmedSnapshot.value = ''; allocation.value = null }
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
          assignment.closed_at ? '已关闭' : stateName[assignment.status] || '状态待更新'
        }}</span>
        <h1>{{ assignment.title }}</h1>
        <p v-if="assignment.type === 'FINAL_PROJECT'">
          {{ assignment.classes.map((c) => c.name).join(' · ') }} · 教师
          {{ Number(assignment.teacher_weight) * 100 }}% / 跨班评审
          {{ Number(assignment.designated_review_weight) * 100 }}%
        </p>
        <p v-else-if="isSubjective">{{ assignment.classes.map((c) => c.name).join(' · ') }} · 在线作答，提交即完成</p>
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
    <div class="toolbar" aria-label="作业管理操作">
      <button class="button button-secondary" :disabled="Boolean(busy)" @click="toggleClosed">{{ assignment.closed_at ? '恢复作业' : '关闭作业' }}</button>
      <button v-if="intakeOpen" class="button button-secondary" :disabled="Boolean(busy)" @click="finishIntake">结束提交</button>
      <button class="button button-secondary" :disabled="Boolean(busy)" @click="removeAssignment">删除作业</button>
    </div>
    <p v-if="assignment.closed_at" class="notice" role="status">作业已关闭，学生提交和评审已暂停。恢复后按原阶段及截止时间继续。</p>
    <section v-if="!assignment.closed_at" class="action-bar">
      <div>
        <h2>下一步</h2>
        <p v-if="isSubjective">{{ assignment.status === 'DRAFT' ? '确认题目、班级与提交截止时间后发布。' : intakeOpen ? '学生在线提交答案即可完成本题，可在下方查看提交情况与答案历史。' : '已停止接收答案，可在下方查看提交与历史版本。' }}</p>
        <p v-else-if="assignment.status === 'DRAFT'">
          {{
            assignment.type === 'PROGRAMMING'
              ? '确认题目和测试用例后发布。'
              : '确认评分标准与两个班级后发布，教师可随时确认当前名单并开始评审。'
          }}发布后不可修改评分规则。
        </p>
        <p v-else-if="assignment.status === 'PUBLISHED'">
          {{
            assignment.type === 'PROGRAMMING'
              ? '学生可以提交代码，测评结果将在下方显示。'
              : '可按当前有效提交生成评审任务，同时继续接收未分配作品。'
          }}
        </p>
        <p v-else-if="assignment.status === 'REVIEWER_GRADING' && intakeOpen">提交与评审同时进行。新作品提交后可补充分配；准备汇总时，先点击“结束提交”。</p>
        <p v-else>
          {{ assignment.type === 'PROGRAMMING' ? '在下方查看学生提交与测评结果。' : ({ SUBMITTING: '可随时按当前有效提交分配跨班评审任务。', REVIEWER_INITIALIZING: '正在分配评审任务，请稍后刷新。', REVIEWER_GRADING: '补齐新增作品的评审任务与评分，再汇总结果。', AGGREGATING: '正在汇总评审结果，请稍后刷新。', TEACHER_GRADING: '完成教师评分与复核后，可发布成绩。', PUBLISHED_RESULT: '成绩已发布，可查看统计并导出。' }[assignment.status] || '请刷新查看作业进度。') }}
        </p>
      </div>
      <button
        v-if="assignment.status === 'DRAFT'"
        class="button"
        :disabled="
          Boolean(busy)
        "
        @click="run(() => publishAssignment(id), 'publish')"
      >
        确认并发布作业</button
      ><button
        v-else-if="
          assignment.type === 'FINAL_PROJECT' &&
          ['PUBLISHED', 'SUBMITTING', 'REVIEWER_INITIALIZING', 'REVIEWER_GRADING'].includes(
            assignment.status,
          )
        "
        class="button"
        :disabled="Boolean(busy) || !canInitialize"
        @click="initialize"
      >
        {{ busy === 'initialize' ? '正在求解并分配…' : '确认并生成跨班任务' }}
      </button>
      <button
        v-if="
          assignment.type === 'FINAL_PROJECT' &&
          ['REVIEWER_GRADING', 'AGGREGATING', 'TEACHER_GRADING'].includes(
            assignment.status,
          )
        "
        class="button"
        :disabled="Boolean(busy) || intakeOpen"
        @click="run(() => aggregateReviews(id), 'aggregate')"
      >
        {{ busy === 'aggregate' ? '正在汇总…' : '汇总评审结果' }}
      </button>
    </section>
    <section v-if="assignment.statement || assignment.topics?.length" class="data-section">
      <h2>题目与知识点</h2><p class="preserve-lines">{{ assignment.statement }}</p>
      <p v-if="assignment.topics?.length">{{ assignment.topics.map(t => `${t.code} · ${t.name}`).join('、') }}</p>
      <RouterLink to="/teacher/learning-analysis">查看学习过程分析</RouterLink>
    </section>
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
        题目已发布。如需修改，请新建作业。
      </p>
    </section>
    <section v-if="assignment.type === 'PROGRAMMING'" class="data-section">
      <div class="section-heading">
        <h2>学生提交与测评结果</h2>
        <button
          class="button button-secondary button-small"
          :disabled="Boolean(busy)"
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
        人通过。
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
              <td>{{ judgeNames[row.status] || '状态待更新' }}</td>
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
    <SubjectiveAnswers v-if="isSubjective" :assignment-id="id" />
    <ProgrammingHistory v-if="assignment.type === 'PROGRAMMING'" :assignment-id="id" :students="Object.values(students).flat()" />
    <section v-if="assignment.type === 'FINAL_PROJECT'" class="data-section">
      <div class="section-heading">
        <div>
          <h2>评分量表</h2>
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
    <section v-if="assignment.type === 'FINAL_PROJECT'" class="data-section" aria-labelledby="allocation-heading">
      <div class="section-heading">
        <div><h2 id="allocation-heading">跨班随机评审分配</h2>
          <p>全体有效提交者参与，每份作品由对方班 5 名不同学生评阅，禁止直接互评。初次分配均衡；补充分配保留已有任务，按累计负担均衡安排新增任务。</p></div>
        <button class="button button-secondary" :disabled="Boolean(busy)" @click="refreshPreview">刷新名单与配额</button>
      </div>
      <template v-if="allocation">
        <p>共 {{ allocation.total_tasks }} 条任务 · 随机种子 {{ allocation.seed }}</p>
        <p v-if="allocation.new_task_count !== undefined">已有 {{ allocation.existing_task_count }} 条任务，本次待新增 {{ allocation.new_task_count }} 条。</p>
        <div class="panel-grid">
          <section v-for="direction in allocation.directions" :key="direction.reviewer_class_id" class="allocation-direction">
            <h3>{{ direction.reviewer_class_name }} → {{ direction.target_class_name }}</h3>
            <p><strong>{{ direction.reviewer_count }}</strong> 人评阅 {{ direction.submission_count }} 份作品</p>
            <p>共 {{ direction.task_count }} 条任务 · {{ allocation.existing_task_count ? '平均负担参考：' : '' }}每人 {{ direction.min_load }}～{{ direction.max_load }} 份</p>
            <details><summary>核对 {{ direction.reviewer_count }} 名参与学生</summary>
              <ul class="participant-list"><li v-for="person in direction.participants" :key="person.id">{{ person.name }} · {{ person.student_no }}</li></ul>
            </details>
          </section>
        </div>
        <p v-if="allocation.blockers.includes('ALLOCATION_INFEASIBLE')" class="notice notice-error" role="alert">当前人数无法同时满足每份五评和禁止直接互评。请先核对两班有效提交人数。</p>
        <p v-if="allocation.blockers.includes('MATERIAL_CHECKS_PENDING')" class="notice" role="status">仍有材料正在检查，名单尚未固定。</p>
        <p v-if="allocation.blockers.includes('REVIEWER_CLASS_CONFLICT')" class="notice notice-error" role="alert">存在班级归属冲突，请检查参与名单。</p>
        <p v-if="allocation.blockers.includes('ANONYMOUS_MATERIAL_NOT_READY')" class="notice" role="status">匿名材料尚未全部就绪。</p>
        <template v-if="!assignment.closed_at && ['PUBLISHED', 'SUBMITTING', 'REVIEWER_INITIALIZING', 'REVIEWER_GRADING'].includes(assignment.status)">
          <p class="muted">生成任务不结束提交。已分配的作品锁定当前版本，后续新作品可再次补充分配；已有任务和评分保持不变。</p>
          <label class="check-row"><input v-model="confirmedSnapshot" type="checkbox" :true-value="allocation.snapshot_hash" false-value="" :disabled="!allocation.ready || Boolean(busy)" />
            <span>我已核对当前参与名单及评阅负担，确认按此快照生成新增任务并继续接收提交。</span></label>
        </template>
        <p v-else-if="['REVIEWER_GRADING', 'AGGREGATING', 'TEACHER_GRADING', 'PUBLISHED_RESULT'].includes(assignment.status)" class="muted">任务已生成。初始配额保存在处理记录中，替补后的实际工作量请查看评审进度。</p>
      </template>
      <p v-else class="muted">请刷新获取当前名单与工作量预览。</p>
    </section>
    <details
      v-if="assignment.type === 'FINAL_PROJECT' && runs.length"
      class="data-section"
    >
      <summary>处理记录</summary>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>评审组</th>
              <th>类型</th>
              <th>状态</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="runItem in runs" :key="runItem.id">
              <td>{{ runItem.started_at ? new Date(runItem.started_at).toLocaleString() : '—' }}</td>
              <td>{{ assignment.classes.find(c => c.id === assignment.panels.find(p => p.id === runItem.panel_id)?.target_class_id)?.name || '跨班评审' }}</td>
              <td>
                {{
                  runItem.algorithm_name === 'panel_bayesian_robust'
                    ? '评审汇总'
                    : '分配评审'
                }}
              </td>
              <td>
                {{
                  { COMPLETED: '已完成', FAILED: '失败', RUNNING: '处理中' }[
                    runItem.status
                  ] || '状态待更新'
                }}
              </td>
              <td>
                {{
                  runItem.parameters_json?.failure_reason ===
                  'INSUFFICIENT_REVIEWS'
                    ? '五人评分未齐，请补齐后重试'
                    : runItem.status === 'FAILED'
                      ? '请稍后重试，或联系课程管理员'
                      : '—'
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
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
 .allocation-direction { padding: 16px 0; }
.participant-list { max-height: 16rem; overflow: auto; }
details {
  padding: 12px 0;
}
</style>
