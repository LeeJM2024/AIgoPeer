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

const classes = ref([]),
  students = ref([]),
  selected = ref(null),
  error = ref(''),
  notice = ref(''),
  busy = ref(false),
  loading = ref(true)
const classForm = reactive({ name: '', course_term: '' }),
  editingId = ref(null),
  importText = ref('')
let requestVersion = 0
async function load() {
  classes.value = await getClasses()
}
async function choose(item) {
  const version = ++requestVersion
  selected.value = item
  students.value = []
  error.value = ''
  importText.value = ''
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
    notice.value = '班级已保存。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
function startEdit(item) {
  editingId.value = item.id
  classForm.name = item.name
  classForm.course_term = item.course_term
}
function cancelEdit() {
  editingId.value = null
  classForm.name = ''
  classForm.course_term = ''
}
async function importRoster() {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const lines = importText.value.split(/\r?\n/).filter((line) => line.trim())
    const rows = lines.map((line, index) => {
      const cells = line.split('\t')
      if (cells.length < 2 || cells.length > 3)
        throw new Error(
          `第 ${index + 1} 行格式不正确，请从表格复制学号、姓名、初始密码三列。`,
        )
      return {
        student_no: cells[0].trim(),
        name: cells[1].trim(),
        password: cells[2] || undefined,
      }
    })
    const result = await importStudents(selected.value.id, rows)
    importText.value = ''
    await load()
    await choose(classes.value.find((c) => c.id === selected.value.id))
    notice.value = `已创建 ${result.created_accounts} 个账号，新增 ${result.new_enrollments} 名班级成员，${result.unchanged} 名已在班内。`
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
        <p>维护课程名册，再从班级学生中配置跨班评审组。</p>
      </div>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <div v-if="loading" class="skeleton-page" aria-label="正在加载班级" />
    <template v-else>
      <form class="data-section" @submit.prevent="saveClass">
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
            v-if="editingId"
            class="button button-secondary"
            type="button"
            :disabled="busy"
            @click="cancelEdit"
          >
            取消编辑</button
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
          <form class="roster-import" @submit.prevent="importRoster">
            <h3>批量添加学生</h3>
            <p class="muted">
              从表格复制“学号、姓名、初始密码”三列，不含表头，每行一人，最多200人。新账号密码至少10位；已有学生可留空，且不会重置密码。任何一行有冲突，整批不写入。
            </p>
            <label
              >学生名单<textarea
                v-model="importText"
                rows="6"
                required
                autocomplete="off"
                spellcheck="false"
                :disabled="busy"
                placeholder="在这里粘贴制表符分隔的名单"
              />
            </label>
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
