<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { currentUser, logout } from './api/auth'
import { getReviewEligibility } from './api/reviewer'
import UiIcon from './components/UiIcon.vue'
import BrandLogo from './components/BrandLogo.vue'
import ChangePasswordDialog from './components/ChangePasswordDialog.vue'

const route = useRoute()
const router = useRouter()
const user = computed(() => route.fullPath && currentUser())
const isTeacher = computed(() => user.value?.role === 'TEACHER')
const isLogin = computed(() => route.meta.public)
const hasReviewTasks = ref(false)
const passwordDialogOpen = ref(false)
const pageLabel = computed(() => {
  const path = route.path
  if (path.includes('/grading')) return '教师评分'
  if (path.includes('/reviews')) return '评审与复核'
  if (path.includes('/statistics')) return '成绩与发布'
  if (path.includes('/project-submission')) return '项目提交'
  if (path.includes('/programming-submission')) return '编程练习'
  if (path.includes('/subjective-submission')) return '在线作答'
  if (path.includes('/learning-analysis')) return '学习过程分析'
  if (path.includes('/grade')) return '成绩反馈'
  if (path.startsWith('/reviewer')) return '匿名评审'
  if (path.startsWith('/teacher/assignments/')) return '作业详情'
  return (
    {
      '/teacher': '课程总览',
      '/teacher/assignments': '作业与评分',
      '/teacher/classes': '班级与学生',
      '/teacher/topics': '知识点目录',
      '/teacher/ai': 'AI 辅助',
      '/student/knowledge': '知识点学习',
      '/student': '我的作业'
    }[path] || '课程工作台'
  )
})
let eligibilityVersion = 0

async function refreshReviewEntry() {
  const version = ++eligibilityVersion
  hasReviewTasks.value = false
  if (user.value?.role !== 'STUDENT') return
  try {
    const result = await getReviewEligibility()
    if (version === eligibilityVersion) hasReviewTasks.value = result.has_tasks
  } catch {
    if (version === eligibilityVersion) hasReviewTasks.value = false
  }
}

function signOut() {
  passwordDialogOpen.value = false
  logout()
  router.push('/login')
}
function sessionExpired() {
  passwordDialogOpen.value = false
  router.replace({ path: '/login', query: { redirect: route.fullPath } })
}
onMounted(() =>
  window.addEventListener('algopeer-session-expired', sessionExpired)
)
onMounted(refreshReviewEntry)
watch(() => route.fullPath, refreshReviewEntry)
onUnmounted(() =>
  window.removeEventListener('algopeer-session-expired', sessionExpired)
)
</script>

<template>
  <main v-if="isLogin" id="main-content" class="login-shell">
    <RouterView />
  </main>
  <div v-else class="app-frame" :class="{ 'student-frame': !isTeacher }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <header class="app-topbar">
      <RouterLink
        class="brand-lockup"
        :to="isTeacher ? '/teacher' : '/student'"
      >
        <BrandLogo />
      </RouterLink>
      <nav v-if="isTeacher" class="app-navigation" aria-label="教师端主导航">
        <RouterLink to="/teacher" exact-active-class="is-active"
          ><UiIcon name="home" />总览</RouterLink
        >
        <RouterLink
          to="/teacher/assignments"
          active-class="is-active"
          :class="{
            'is-active': route.path.startsWith('/teacher/assignments')
          }"
          ><UiIcon name="assignments" />作业与评分</RouterLink
        >
        <RouterLink to="/teacher/classes" active-class="is-active"
          ><UiIcon name="people" />班级与学生</RouterLink
        >
        <RouterLink to="/teacher/topics" active-class="is-active"
          ><UiIcon name="book" />知识点目录</RouterLink
        >
        <RouterLink to="/teacher/learning-analysis" active-class="is-active"><UiIcon name="book" />学习分析</RouterLink>
        <RouterLink to="/teacher/ai" active-class="is-active"
          ><UiIcon name="video" />AI 辅助</RouterLink
        >
      </nav>
      <nav v-else class="app-navigation" aria-label="学生端主导航">
        <RouterLink
          to="/student"
          active-class="is-active"
          :class="{ 'is-active': route.path === '/student' || route.path.startsWith('/student/assignments/') }"
          ><UiIcon name="assignments" />我的作业</RouterLink
        >
        <RouterLink to="/student/knowledge" active-class="is-active"><UiIcon name="book" />知识点学习</RouterLink>
        <RouterLink
          v-if="hasReviewTasks"
          to="/reviewer/tasks"
          active-class="is-active"
          ><UiIcon name="review" />评审任务</RouterLink
        >
      </nav>
      <div class="account-block">
        <span class="account-avatar" aria-hidden="true">{{
          user?.name?.slice(0, 1) || 'A'
        }}</span>
        <div class="account-details">
          <strong>{{ user?.name || '课程用户' }}</strong
          ><small>{{ isTeacher ? '任课教师' : '学生' }}</small>
        </div>
        <button
          v-if="user"
          class="account-password"
          type="button"
          aria-label="修改密码"
          title="修改密码"
          aria-haspopup="dialog"
          @click="passwordDialogOpen = true"
        >
          <UiIcon name="shield" /><span>修改密码</span>
        </button>
        <button
          class="account-logout"
          type="button"
          aria-label="退出登录"
          title="退出登录"
          @click="signOut"
        >
          <UiIcon name="logout" />
        </button>
      </div>
    </header>
    <ChangePasswordDialog v-if="passwordDialogOpen" @close="passwordDialogOpen = false" />
    <div class="workspace-frame">
      <div
        v-if="!['/teacher', '/student'].includes(route.path)"
        class="workspace-header"
      >
        <div class="workspace-location">
          <span>算法设计与分析</span><UiIcon name="chevron" /><strong>{{
            pageLabel
          }}</strong>
        </div>
        <span class="workspace-role">{{
          isTeacher ? '教师空间' : '学生空间'
        }}</span>
      </div>
      <main id="main-content" class="workspace" tabindex="-1">
        <RouterView v-slot="{ Component }"
          ><Transition name="page" mode="out-in"
            ><component :is="Component" /></Transition
        ></RouterView>
      </main>
      <footer class="workspace-footer">
        <span>网络空间安全学院 · 算法设计与分析</span
        ><span>让学习有反馈，让评价有依据</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.account-password {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 44px;
  min-width: 44px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--control-radius);
  color: var(--muted);
  background: var(--surface-translucent);
  white-space: nowrap;
  font-size: 13px;
}
.account-password:hover { color: var(--primary); background: var(--primary-soft); }
@media (max-width: 1100px) {
  .account-password { padding: 0; }
  .account-password span { display: none; }
}
</style>
