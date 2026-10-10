import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ReviewerTasksView from '../views/ReviewerTasksView.vue'
import StudentWorkspaceView from '../views/student/StudentWorkspaceView.vue'
import StudentProjectSubmissionView from '../views/student/StudentProjectSubmissionView.vue'
import StudentProgrammingSubmissionView from '../views/student/StudentProgrammingSubmissionView.vue'
import StudentGradeView from '../views/student/StudentGradeView.vue'
import LoginView from '../views/LoginView.vue'
import TeacherDashboardView from '../views/teacher/TeacherDashboardView.vue'
import TeacherAssignmentsView from '../views/teacher/TeacherAssignmentsView.vue'
import TeacherAssignmentView from '../views/teacher/TeacherAssignmentView.vue'
import TeacherGradingView from '../views/teacher/TeacherGradingView.vue'
import TeacherClassesView from '../views/teacher/TeacherClassesView.vue'
import TeacherTopicsView from '../views/teacher/TeacherTopicsView.vue'
import TeacherReviewView from '../views/teacher/TeacherReviewView.vue'
import TeacherStatisticsView from '../views/teacher/TeacherStatisticsView.vue'
import TeacherAiSettingsView from '../views/teacher/TeacherAiSettingsView.vue'
import { currentUser } from '../api/auth'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/teacher/topics',
      component: TeacherTopicsView,
      meta: { teacher: true },
    },
    { path: '/', component: HomeView },
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/student', component: StudentWorkspaceView },
    {
      path: '/student/assignments/:assignmentId/project-submission',
      component: StudentProjectSubmissionView,
      props: true,
    },
    {
      path: '/student/assignments/:assignmentId/programming-submission',
      component: StudentProgrammingSubmissionView,
      props: true,
    },
    {
      path: '/student/assignments/:assignmentId/grade',
      component: StudentGradeView,
      props: true,
    },
    { path: '/reviewer/tasks', component: ReviewerTasksView },
    {
      path: '/teacher',
      component: TeacherDashboardView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/classes',
      component: TeacherClassesView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/assignments',
      component: TeacherAssignmentsView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/assignments/:id',
      component: TeacherAssignmentView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/assignments/:id/grading',
      component: TeacherGradingView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/assignments/:id/reviews',
      component: TeacherReviewView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/assignments/:id/statistics',
      component: TeacherStatisticsView,
      meta: { teacher: true },
    },
    {
      path: '/teacher/ai-video',
      component: TeacherAiSettingsView,
      meta: { teacher: true },
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.teacher && currentUser()?.role !== 'TEACHER')
    return { path: '/login', query: { redirect: to.fullPath } }
})

export default router
