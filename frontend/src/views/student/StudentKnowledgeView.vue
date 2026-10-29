<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getAiTopics } from '../../api/ai'
import AiConversation from '../../components/AiConversation.vue'
const route = useRoute(), router = useRouter()
const topics = ref([]), search = ref(''), chapter = ref(''), loading = ref(true), error = ref('')
const chapters = computed(() => [...new Set(topics.value.map(item => item.chapter))])
const filtered = computed(() => topics.value.filter(item => (!chapter.value || item.chapter === chapter.value) && `${item.name} ${item.chapter} ${item.description}`.toLowerCase().includes(search.value.toLowerCase())))
const selected = computed(() => topics.value.find(item => String(item.id) === String(route.query.topic)) || topics.value[0])
async function load() { loading.value = true; error.value = ''; try { topics.value = await getAiTopics() } catch (err) { error.value = err.message } finally { loading.value = false } }
onMounted(load)
function choose(item) { router.replace({ query: { topic: String(item.id) } }) }
</script>
<template>
  <div class="view-stack"><header class="page-heading"><div><p class="eyebrow">LEARN THE IDEA</p><h1>知识点学习</h1><p class="muted">从一个具体问题开始，把算法的思路、过程与证明讲清楚。</p></div></header>
    <p v-if="loading" role="status">正在加载课程知识点…</p><p v-if="error" class="notice notice-error" role="alert">{{ error }} <button class="button button-secondary button-small" @click="load">重试</button></p>
    <div v-if="!loading && topics.length" class="knowledge-layout"><aside class="topic-catalog"><label for="topic-search">查找知识点</label><input id="topic-search" v-model="search" type="search" placeholder="算法名称或关键词" /><label for="topic-chapter">所属章节</label><select id="topic-chapter" v-model="chapter"><option value="">全部章节</option><option v-for="name in chapters" :key="name">{{ name }}</option></select><nav class="topic-list" aria-label="课程知识点"><button v-for="item in filtered" :key="item.id" :class="{ selected: selected?.id === item.id }" :aria-pressed="selected?.id === item.id" @click="choose(item)"><small>{{ item.chapter }}</small><strong>{{ item.name }}</strong></button><p v-if="!filtered.length" class="muted">没有匹配的知识点。</p></nav></aside>
      <article v-if="selected" class="topic-workspace"><header class="topic-intro"><span class="eyebrow">{{ selected.chapter }}</span><h2>{{ selected.name }}</h2><p>{{ selected.description }}</p></header><AiConversation :key="selected.id" mode="KNOWLEDGE" :context-id="selected.id" /></article>
    </div><p v-else-if="!loading && !error" class="empty-state">课程尚未设置知识点。</p>
  </div>
</template>
<style scoped>
.knowledge-layout { display: grid; grid-template-columns: 290px minmax(0,1fr); gap: 32px; align-items: start; } .topic-catalog { display: grid; gap: 10px; } label { font-size: 13px; font-weight: 600; }
input,select { width: 100%; box-sizing: border-box; padding: 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface,white); color: var(--ink); }
.topic-list { display: grid; gap: 6px; max-height: 620px; overflow: auto; margin-top: 8px; } .topic-list button { display: grid; gap: 6px; padding: 14px 16px; text-align: left; border: 1px solid transparent; border-radius: 16px; color: var(--ink); background: transparent; cursor: pointer; font: inherit; }
.topic-list button.selected { background: var(--primary-soft); border-color: var(--primary); } .topic-list small { color: var(--muted); font-size: 12px; } .topic-list strong { font-weight: 600; font-size: 14px; }
.topic-workspace { min-width: 0; padding: 30px; border-radius: 28px; background: var(--surface,white); } .topic-intro { border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; } .topic-intro h2 { font-size: 28px; margin: 12px 0; } .topic-intro p { color: var(--muted); line-height: 1.8; }
@media(max-width:850px) { .knowledge-layout { grid-template-columns: 1fr; } .topic-list { max-height: 220px; } .topic-workspace { padding: 20px; } }
</style>
