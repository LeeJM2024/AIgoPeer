<script setup>
defineProps({ problem: { type: Object, required: true } })
</script>
<template>
  <section class="data-section problem-editor">
    <h3>题目与测试用例</h3>
    <p class="muted">
      公开样例会展示给学生；隐藏用例只用于判题。发布后题目和用例不可修改。
    </p>
    <label
      >题面<textarea
        v-model="problem.statement"
        rows="5"
        required
        maxlength="20000"
      />
    </label>
    <div class="form-grid">
      <label
        >输入说明<textarea
          v-model="problem.input_description"
          rows="3"
          required
          maxlength="10000"
        />
      </label>
      <label
        >输出说明<textarea
          v-model="problem.output_description"
          rows="3"
          required
          maxlength="10000"
        />
      </label>
      <label
        >每个用例时限（毫秒）<input
          v-model.number="problem.time_limit_ms"
          type="number"
          min="100"
          max="10000"
          required
      /></label>
      <label
        >内存限制（MB）<input
          v-model.number="problem.memory_limit_mb"
          type="number"
          min="16"
          max="1024"
          required
      /></label>
    </div>
    <fieldset
      v-for="(item, index) in problem.test_cases"
      :key="index"
      class="test-case"
    >
      <legend>
        用例 {{ index + 1 }} · {{ item.is_public ? '公开样例' : '隐藏用例' }}
      </legend>
      <div class="form-grid">
        <label
          >输入<textarea
            v-model="item.input_data"
            rows="3"
            spellcheck="false"
            maxlength="65536"
          />
        </label>
        <label
          >预期输出<textarea
            v-model="item.expected_output"
            rows="3"
            spellcheck="false"
            maxlength="65536"
          />
        </label>
      </div>
      <div class="toolbar">
        <label class="check-row"
          ><input
            v-model="item.is_public"
            type="checkbox"
          />向学生展示此样例</label
        >
        <button
          type="button"
          class="button button-secondary button-small"
          :disabled="problem.test_cases.length <= 2"
          @click="problem.test_cases.splice(index, 1)"
        >
          删除用例 {{ index + 1 }}
        </button>
      </div>
    </fieldset>
    <button
      class="button button-secondary"
      type="button"
      :disabled="problem.test_cases.length >= 100"
      @click="
        problem.test_cases.push({
          input_data: '',
          expected_output: '',
          is_public: false,
        })
      "
    >
      添加测试用例
    </button>
    <p class="muted">
      至少保留一个公开样例和一个隐藏用例，建议准备 2 个公开、3
      个隐藏用例。输入和输出的空白字符会原样保存。
    </p>
  </section>
</template>
<style scoped>
.problem-editor {
  display: grid;
  gap: 16px;
}
.test-case {
  padding: 16px;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 0;
}
.test-case .toolbar {
  margin-top: 12px;
  justify-content: space-between;
}
textarea {
  width: 100%;
}
</style>
