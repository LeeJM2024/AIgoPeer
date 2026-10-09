<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  createTopic,
  deleteTopic,
  getTopics,
  updateTopic,
} from '../../api/teacher'
const rows = ref([]),
  error = ref(''),
  notice = ref(''),
  busy = ref(false),
  editing = ref(null)
const form = reactive({
  code: '',
  chapter: '',
  name: '',
  description: '',
  expected_updated_at: null,
})
async function load() {
  rows.value = await getTopics()
}
function reset() {
  editing.value = null
  Object.assign(form, {
    code: '',
    chapter: '',
    name: '',
    description: '',
    expected_updated_at: null,
  })
}
function edit(row) {
  editing.value = row.id
  Object.assign(form, {
    code: row.code,
    chapter: row.chapter,
    name: row.name,
    description: row.description,
    expected_updated_at: row.updated_at,
  })
  window.scrollTo({ top: 0, behavior: 'auto' })
}
async function save() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    if (editing.value) await updateTopic(editing.value, form)
    else await createTopic(form)
    reset()
    await load()
    notice.value = '知识点已保存，学生认领目录将同步更新。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
async function remove(row) {
  if (!confirm(`删除尚未被认领的知识点“${row.name}”？`)) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await deleteTopic(row.id)
    if (editing.value === row.id) reset()
    await load()
    notice.value = '知识点已删除。'
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  try {
    await load()
  } catch (err) {
    error.value = err.message
  }
})
</script>
<template>
  <div class="view-stack">
    <header class="page-heading">
      <div>
        <h1>知识点目录</h1>
        <p>
          维护学生可认领的课程知识点。已被认领的条目保留原样，避免改变历史作业依据。
        </p>
      </div>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice notice-success" role="status">
      {{ notice }}
    </p>
    <form class="editor-panel" @submit.prevent="save">
      <h2>{{ editing ? '编辑知识点' : '新增知识点' }}</h2>
      <fieldset class="bare-fieldset form-grid" :disabled="busy">
        <label
          >编号<input
            v-model="form.code"
            aria-label="编号"
            required
            maxlength="8"
            pattern="(?:[A-Za-z0-9_]|-)+"
          /><small>最多8位字母、数字、下划线或连字符</small></label
        >
        <label
          >章节<input v-model="form.chapter" required maxlength="100"
        /></label>
        <label class="span-2"
          >知识点名称<input v-model="form.name" required maxlength="200"
        /></label>
        <label class="span-2"
          >说明<textarea
            v-model="form.description"
            rows="3"
            maxlength="10000"
          />
        </label>
      </fieldset>
      <div class="form-actions">
        <button
          v-if="editing"
          type="button"
          class="button button-secondary"
          :disabled="busy"
          @click="reset"
        >
          取消编辑</button
        ><button class="button" :disabled="busy">
          {{ busy ? '正在保存…' : '保存知识点' }}
        </button>
      </div>
    </form>
    <section class="data-section">
      <h2>课程目录</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>编号</th>
              <th>章节 / 知识点</th>
              <th>认领次数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>{{ row.code }}</td>
              <td>
                <strong>{{ row.name }}</strong
                ><small>{{ row.chapter }}</small>
                <p>{{ row.description }}</p>
              </td>
              <td>{{ row.claim_count }}</td>
              <td>
                <span v-if="row.claim_count" class="muted"
                  >已认领，保留历史</span
                >
                <div v-else class="toolbar">
                  <button
                    class="button button-secondary button-small"
                    :disabled="busy"
                    @click="edit(row)"
                  >
                    编辑</button
                  ><button
                    class="button button-secondary button-small"
                    :disabled="busy"
                    @click="remove(row)"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!rows.length" class="empty-state">
        暂无知识点，请先添加课程目录。
      </p>
    </section>
  </div>
</template>
