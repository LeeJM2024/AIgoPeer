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
const pageLabel = computed(() => {
  const path = route.path
  if (path.includes('/grading')) return '教师评分'
  if (path.includes('/reviews')) return '评审与复核'
  if (path.includes('/statistics')) return '成绩与发布'
  if (path.includes('/project-submission')) return '项目提交'
  if (path.includes('/programming-submission')) return '编程练习'
  if (path.includes('/grade')) return '成绩反馈'
  if (path.startsWith('/reviewer')) return '匿名评审'
  if (path.startsWith('/teacher/assignments/')) return '作业详情'
  return { '/teacher': '课程总览', '/teacher/assignments': '作业与评分', '/teacher/classes': '班级与学生', '/teacher/topics': '知识点目录', '/teacher/ai-video': '视频辅助评阅', '/student': '我的作业' }[path] || '课程工作台'
})
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
  <div v-else class="app-frame" :class="{ 'student-frame': !isTeacher }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside class="side-rail">
      <RouterLink class="brand-lockup" :to="isTeacher ? '/teacher' : '/student'">
        <span class="brand-mark"><UiIcon name="code" /></span
        ><span><strong>AlgoPeer</strong><small>算法课程工作台</small></span>
      </RouterLink>
      <div class="course-identity"><span class="course-monogram">A</span><div><strong>算法设计与分析</strong><small>{{ isTeacher ? '教学管理空间' : '我的学习空间' }}</small></div></div>
      <p class="nav-caption">{{ isTeacher ? '课程管理' : '学习工作台' }}</p>
      <nav v-if="isTeacher" aria-label="教师端主导航">
        <RouterLink to="/teacher" exact-active-class="is-active"
          ><UiIcon name="home" />总览</RouterLink
        >
        <RouterLink to="/teacher/assignments" active-class="is-active" :class="{ 'is-active': route.path.startsWith('/teacher/assignments') }"
          ><UiIcon name="assignments" />作业与评分</RouterLink
        >
        <RouterLink to="/teacher/classes" active-class="is-active"
          ><UiIcon name="people" />班级与学生</RouterLink
        >
        <RouterLink to="/teacher/topics" active-class="is-active"
          ><UiIcon name="book" />知识点目录</RouterLink
        >
      </nav>
      <nav v-else aria-label="学生端主导航">
        <RouterLink to="/student" active-class="is-active" :class="{ 'is-active': route.path.startsWith('/student') }"><UiIcon name="assignments" />我的作业</RouterLink>
        <RouterLink v-if="hasReviewTasks" to="/reviewer/tasks" active-class="is-active"><UiIcon name="review" />评审任务</RouterLink>
      </nav>
      <nav v-if="isTeacher" class="secondary-nav" aria-label="辅助工具">
        <p class="nav-caption">辅助工具</p>
        <RouterLink to="/teacher/ai-video" active-class="is-active"><UiIcon name="video" />视频辅助评阅</RouterLink>
      </nav>
      <div class="rail-note"><UiIcon name="code" /><strong>每一种解法，都值得探索</strong><p>从理解原理到动手实现，记录算法课堂里的每一步。</p></div>
      <div class="account-block">
        <span class="account-avatar" aria-hidden="true">{{ user?.name?.slice(0, 1) || 'A' }}</span>
        <div class="account-details"><strong>{{ user?.name || '课程用户' }}</strong><small>{{ isTeacher ? '任课教师' : '学生' }}</small></div>
        <button class="account-logout" type="button" aria-label="退出登录" title="退出登录" @click="signOut"><UiIcon name="logout" /></button>
      </div>
    </aside>
    <div class="workspace-frame">
      <header class="workspace-header"><div class="workspace-location"><span>课程工作台</span><UiIcon name="chevron" /><strong>{{ pageLabel }}</strong></div><span class="workspace-role"><span class="role-indicator" />{{ isTeacher ? '教师空间' : '学生空间' }}</span></header>
      <main id="main-content" class="workspace" tabindex="-1"><RouterView v-slot="{ Component }"><Transition name="page" mode="out-in"><component :is="Component" /></Transition></RouterView></main>
      <footer class="workspace-footer"><span>AlgoPeer · 算法设计与分析</span><span>让学习有反馈，让评价有依据</span></footer>
    </div>
  </div>
</template>
