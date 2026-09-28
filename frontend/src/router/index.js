import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ReviewerTasksView from '../views/ReviewerTasksView.vue'
import StudentWorkspaceView from '../views/student/StudentWorkspaceView.vue'
import StudentProjectSubmissionView from '../views/student/StudentProjectSubmissionView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/student', component: StudentWorkspaceView },
    {
      path: '/student/assignments/:assignmentId/project-submission',
      component: StudentProjectSubmissionView,
      props: true
    },
    { path: '/reviewer/tasks', component: ReviewerTasksView }
  ]
})
