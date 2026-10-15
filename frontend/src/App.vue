<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { currentUser, logout } from './api/auth'
import { getReviewEligibility } from './api/reviewer'
import UiIcon from './components/UiIcon.vue'

const route = useRoute()
const router = useRouter()
const user = computed(() => route.fullPath && currentUser())
const isTeacher = computed(() => user.value?.role === 'TEACHER')
const isLogin = computed(() => route.meta.public)
const hasReviewTasks = ref(false)
let eligibilityVersion = 0

async function refreshReviewEntry() {
  const version = ++eligibilityVersion
  hasReviewTasks.value = false
  if (user.value?.role !== 'STUDENT') return
  try { const result = await getReviewEligibility(); if (version === eligibilityVersion) hasReviewTasks.value = result.has_tasks }
  catch { if (version === eligibilityVersion) hasReviewTasks.value = false }
}

function signOut() {
  logout()
  router.push('/login')
}
function sessionExpired() {
  router.replace({ path: '/login', query: { redirect: route.fullPath } })
}
onMounted(() =>
  window.addEventListener('algopeer-session-expired', sessionExpired),
)
onMounted(refreshReviewEntry)
watch(() => route.fullPath, refreshReviewEntry)
onUnmounted(() =>
  window.removeEventListener('algopeer-session-expired', sessionExpired),
)
</script>

<template>
  <main v-if="isLogin" id="main-content" class="login-shell"><RouterView /></main>
  <div v-else-if="isTeacher" class="app-frame">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside class="side-rail">
      <RouterLink class="brand-lockup" to="/teacher">
        <span class="brand-mark"><UiIcon name="book" /></span
        ><span><strong>AlgoPeer</strong><small>教师工作台</small></span>
      </RouterLink>
      <nav aria-label="教师端主导航">
        <RouterLink to="/teacher" exact-active-class="is-active"
          ><UiIcon name="home" />总览</RouterLink
        >
        <RouterLink to="/teacher/assignments" active-class="is-active"
          ><UiIcon name="assignments" />作业与评分</RouterLink
        >
        <RouterLink to="/teacher/classes" active-class="is-active"
          ><UiIcon name="people" />班级与学生</RouterLink
        >
        <RouterLink to="/teacher/topics" active-class="is-active"
          ><UiIcon name="book" />知识点目录</RouterLink
        >
      </nav>
      <nav class="secondary-nav" aria-label="辅助工具">
        <RouterLink to="/teacher/ai-video" active-class="is-active"><UiIcon name="video" />视频辅助评阅</RouterLink>
      </nav>
      <div class="account-block">
        <span>{{ user?.name }}</span
        ><small>教师</small
        ><button class="text-button" type="button" @click="signOut">
          <UiIcon name="logout" />退出登录
        </button>
      </div>
    </aside>
    <div class="workspace-frame">
      <header class="workspace-header"><span>算法设计与分析</span><span class="workspace-role">教师端</span></header>
      <main id="main-content" class="workspace"><RouterView /></main>
    </div>
  </div>
  <template v-else>
    <header class="public-header">
      <RouterLink class="brand" to="/">AlgoPeer</RouterLink>
      <nav>
        <RouterLink to="/student">我的作业</RouterLink
        ><RouterLink v-if="hasReviewTasks" to="/reviewer/tasks">评审任务</RouterLink>
      </nav>
      <RouterLink v-if="!user" class="button button-small" to="/login"
        >登录</RouterLink
      >
      <button v-else class="text-button light" @click="signOut">退出</button>
    </header>
    <main class="page-shell"><RouterView /></main>
  </template>
</template>
