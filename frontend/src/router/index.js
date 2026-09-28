import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ReviewerTasksView from '../views/ReviewerTasksView.vue'
import StudentWorkspaceView from '../views/student/StudentWorkspaceView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/student', component: StudentWorkspaceView },
    { path: '/reviewer/tasks', component: ReviewerTasksView }
  ]
})
