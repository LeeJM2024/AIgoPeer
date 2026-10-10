<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { currentUser, logout } from './api/auth'
import { getMyReviewTasks } from './api/reviewer'

const route = useRoute()
const router = useRouter()
const user = computed(() => route.fullPath && currentUser())
const isTeacher = computed(() => user.value?.role === 'TEACHER')
const hasReviewTasks = ref(false)

async function refreshReviewEntry() {
  hasReviewTasks.value = false
  if (user.value?.role !== 'STUDENT') return
  try { hasReviewTasks.value = (await getMyReviewTasks()).length > 0 }
  catch { hasReviewTasks.value = false }
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
  <div v-if="isTeacher" class="app-frame">
    <aside class="side-rail">
      <RouterLink class="brand-lockup" to="/teacher">
        <span class="brand-mark">A</span
        ><span><strong>AlgoPeer</strong><small>教师工作台</small></span>
      </RouterLink>
      <nav aria-label="教师端主导航">
        <RouterLink to="/teacher" exact-active-class="is-active"
          >总览</RouterLink
        >
        <RouterLink to="/teacher/assignments" active-class="is-active"
          >作业与评分</RouterLink
        >
        <RouterLink to="/teacher/classes" active-class="is-active"
          >班级与学生</RouterLink
        >
        <RouterLink to="/teacher/ai-video" active-class="is-active"
          >视频智能分析</RouterLink
        >
        <RouterLink to="/teacher/topics" active-class="is-active"
          >知识点目录</RouterLink
        >
      </nav>
      <div class="account-block">
        <span>{{ user?.name }}</span
        ><small>教师</small
        ><button class="text-button" type="button" @click="signOut">
          退出登录
        </button>
      </div>
    </aside>
    <main class="workspace"><RouterView /></main>
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
