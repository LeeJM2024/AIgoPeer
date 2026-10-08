<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  getAssignment,
  getClassStudents,
  initializeReviewTasks,
  publishAssignment,
  savePanels,
} from '../../api/teacher'

const route = useRoute()
const assignment = ref(null)
const students = ref({})
const selections = ref({})
const error = ref('')
const notice = ref('')
const busy = ref('')
const id = Number(route.params.id)
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
        <p>
          {{ assignment.classes.map((c) => c.name).join(' · ') }} · 教师
          {{ Number(assignment.teacher_weight) * 100 }}% / 跨班评审
          {{ Number(assignment.designated_review_weight) * 100 }}%
        </p>
      </div>
      <RouterLink
        class="button button-secondary"
        :to="`/teacher/assignments/${id}/grading`"
        >进入评分工作台</RouterLink
      >
    </header>
    <nav class="toolbar" aria-label="作业工作区">
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
    <section class="data-section">
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
    <section class="data-section">
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
          确认 Rubric 和两个评审组后发布；发布后规则将被冻结。
        </p>
        <p v-else-if="assignment.status === 'PUBLISHED'">
          提交截止后可根据所有 VALID 作业生成评审任务。
        </p>
        <p v-else>
          当前状态：{{ assignment.status }}。任务和成绩记录会保留审计痕迹。
        </p>
      </div>
      <button
        v-if="assignment.status === 'DRAFT'"
        class="button"
        :disabled="busy || assignment.panels.length !== 2"
        @click="run(() => publishAssignment(id), 'publish')"
      >
        确认并发布作业</button
      ><button
        v-else-if="
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
    </section>
  </div>
  <div v-else class="view-stack">
    <p v-if="error" class="notice notice-error">加载失败：{{ error }}</p>
    <div v-else class="skeleton-page" />
  </div>
</template>
