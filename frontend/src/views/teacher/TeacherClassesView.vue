<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  createClass,
  editClass,
  getClasses,
  getClassStudents,
  importStudents,
  removeEnrollment,
} from '../../api/teacher'

const showForm = ref(false)
const classes = ref([]),
  students = ref([]),
  selected = ref(null),
  error = ref(''),
  importError = ref(''),
  notice = ref(''),
  busy = ref(false),
  loading = ref(true)
const classForm = reactive({ name: '', course_term: '' }),
  editingId = ref(null),
  importText = ref('')
const studentForm = reactive({ student_no: '', name: '', password: '' })
let requestVersion = 0
async function load() {
  classes.value = await getClasses()
}
async function choose(item) {
  const version = ++requestVersion
  selected.value = item
  students.value = []
  error.value = ''
  importError.value = ''
  importText.value = ''
  studentForm.student_no = ''
  studentForm.name = ''
  studentForm.password = ''
  try {
    const rows = await getClassStudents(item.id)
    if (version === requestVersion) students.value = rows
  } catch (err) {
    if (version === requestVersion) error.value = err.message
  }
}
onMounted(async () => {
  try {
    await load()
    if (classes.value.length) await choose(classes.value[0])
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
})
async function saveClass() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = editingId.value
      ? await editClass(editingId.value, classForm)
      : await createClass(classForm)
    await load()
    await choose(classes.value.find((c) => c.id === result.class_id))
    editingId.value = null
    classForm.name = ''
    classForm.course_term = ''
    showForm.value = false
    notice.value = '班级已保存。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
function startEdit(item) {
  showForm.value = true
  window.scrollTo({ top: 0, behavior: 'auto' })
  editingId.value = item.id
  classForm.name = item.name
  classForm.course_term = item.course_term
}
function cancelEdit() {
  showForm.value = false
  editingId.value = null
  classForm.name = ''
  classForm.course_term = ''
}
async function importRoster() {
  if (busy.value || !selected.value) return
  error.value = ''
  importError.value = ''
  notice.value = ''
  busy.value = true
  try {
    const rows = importText.value.split(/\r?\n/).map((line, index) => {
      if (!line.trim()) return null
      const cells = line.includes('\t') ? line.split('\t') : line.trim().split(/\s+/)
      if (cells.length < 2 || cells.length > 3 || !cells[0].trim() || !cells[1].trim())
        throw new Error(
          `第 ${index + 1} 行格式不正确：请用空格或制表符分隔学号、姓名、初始密码；姓名或密码含空格时，请从表格复制三列。`,
        )
      return {
        student_no: cells[0].trim(),
        name: cells[1].trim(),
        password: cells[2] || undefined,
      }
    }).filter(Boolean)
    if (!rows.length) throw new Error('请填写学生名单。')
    const result = await importStudents(selected.value.id, rows)
    importText.value = ''
    await load()
    await choose(classes.value.find((c) => c.id === selected.value.id))
    notice.value = `已创建 ${result.created_accounts} 个账号，新增 ${result.new_enrollments} 名班级成员，${result.unchanged} 名已在班内。`
  } catch (err) {
    importError.value = err.message
  } finally {
    busy.value = false
  }
}
async function addStudent() {
  if (busy.value || !selected.value) return
  error.value = ''
  notice.value = ''
  const student = {
    student_no: studentForm.student_no.trim(),
    name: studentForm.name.trim(),
    password: studentForm.password,
  }
  if (!student.student_no || !student.name) {
    error.value = '请填写学生的学号和姓名。'
    return
  }
  if (student.password.length < 10 || student.password.length > 128 || !student.password.trim()) {
    error.value = '初始密码须为 10～128 位，不能全为空格。'
    return
  }
  busy.value = true
  try {
    const classId = selected.value.id
    await importStudents(classId, [student])
    await load()
    await choose(classes.value.find((c) => c.id === classId))
    notice.value = `已将 ${student.name}（${student.student_no}）添加到当前班级。`
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function remove(student) {
  if (!confirm(`将 ${student.name} 移出当前班级？账号仍会保留。`)) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await removeEnrollment(selected.value.id, student.id)
    await load()
    await choose(classes.value.find((c) => c.id === selected.value.id))
    notice.value = '已移出班级。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="view-stack">
    <header class="page-heading">
      <div>
        <h1>班级与学生</h1>
      </div>
      <button class="button" :disabled="busy || loading" @click="cancelEdit(); showForm = true">新建班级</button>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <div v-if="loading" class="skeleton-page" aria-label="正在加载班级" />
    <template v-else>
      <form v-if="showForm" class="data-section" @submit.prevent="saveClass">
        <h2>{{ editingId ? '编辑班级' : '新建班级' }}</h2>
        <fieldset class="form-grid bare-fieldset" :disabled="busy">
          <label
            >班级名称<input
              v-model="classForm.name"
              required
              maxlength="100" /></label
          ><label
            >学期<input
              v-model="classForm.course_term"
              required
              maxlength="64"
              placeholder="例如：2026年秋季"
          /></label>
        </fieldset>
        <div class="form-actions">
          <button
            class="button button-secondary"
            type="button"
            :disabled="busy"
            @click="cancelEdit"
          >
            取消</button
          ><button class="button" :disabled="busy">保存班级</button>
        </div>
      </form>
      <section class="data-section">
        <div class="section-heading">
          <h2>班级名册</h2>
          <label
            >选择班级<select
              :value="selected?.id"
              :disabled="busy"
              @change="
                choose(
                  classes.find((c) => c.id === Number($event.target.value)),
                )
              "
            >
              <option v-for="item in classes" :key="item.id" :value="item.id">
                {{ item.name }} · {{ item.course_term }}（{{
                  item.student_count
                }}人）
              </option>
            </select></label
          >
        </div>
        <div v-if="selected">
          <button
            class="button button-secondary button-small"
            :disabled="busy"
            @click="startEdit(selected)"
          >
            编辑当前班级
          </button>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>学号</th>
                  <th>姓名</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="student in students" :key="student.id">
                  <td>{{ student.student_no }}</td>
                  <td>{{ student.name }}</td>
                  <td>
                    <button
                      class="button button-secondary button-small"
                      :disabled="busy"
                      @click="remove(student)"
                    >
                      移出班级
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!students.length" class="empty-state compact">
            班级暂无学生，可在下方添加。
          </p>
          <form class="roster-import student-add-form" aria-label="添加学生" @submit.prevent="addStudent">
            <h3>添加学生</h3>
            <p class="muted">学号用作登录账号，姓名用作页面显示名称。学生登录后，右上角显示姓名，作业、评审和成绩均关联该学生账号。</p>
            <fieldset class="form-grid bare-fieldset" :disabled="busy">
              <label for="student-account">学号（登录账号）<input id="student-account" v-model="studentForm.student_no" maxlength="32" autocomplete="off" required /></label>
              <label for="student-display-name">姓名（显示名称）<input id="student-display-name" v-model="studentForm.name" maxlength="100" autocomplete="off" required /></label>
              <label for="student-initial-password">初始密码<input id="student-initial-password" v-model="studentForm.password" type="password" minlength="10" maxlength="128" autocomplete="new-password" required /></label>
            </fieldset>
            <div class="form-actions"><button class="button" type="submit" :disabled="busy">{{ busy ? '正在保存…' : '添加到当前班级' }}</button></div>
          </form>
          <form class="roster-import" aria-label="批量添加学生" @submit.prevent="importRoster">
            <h3>批量添加学生</h3>
            <p class="muted">
              每行填写“学号 姓名 初始密码”，用一个或多个空格分隔，也可从表格复制三列，不含表头，每行一人，最多200人。姓名或密码含空格时，请从表格复制，保留制表符分隔。新账号密码至少10位；已有账号填写原学号和姓名，初始密码可留空。导入不会重置已有密码，任何一行有冲突，整批不写入。学生登录后可在右上角修改密码。
            </p>
            <label
              >学生名单<textarea
                v-model="importText"
                rows="6"
                required
                autocomplete="off"
                spellcheck="false"
                :disabled="busy"
                :aria-invalid="!!importError"
                :aria-describedby="importError ? 'roster-import-error' : undefined"
                placeholder="学号 姓名 初始密码（支持空格或表格制表符分隔）"
              />
            </label>
            <p v-if="importError" id="roster-import-error" class="notice notice-error" role="alert">{{ importError }}</p>
            <div class="form-actions">
              <button class="button" :disabled="busy || !importText.trim()">
                {{ busy ? '正在保存…' : '导入到当前班级' }}
              </button>
            </div>
          </form>
        </div>
        <p v-else class="empty-state">先创建一个班级，再添加学生。</p>
      </section>
    </template>
  </div>
</template>
