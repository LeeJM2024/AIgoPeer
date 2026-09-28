import { apiFetch } from './client'

export const getMyReviewTasks = (status = 'PENDING') =>
  apiFetch(`/api/reviewer/review-tasks/mine?status=${encodeURIComponent(status)}`)

export const submitReview = (taskId, payload) =>
  apiFetch(`/api/reviewer/review-tasks/${taskId}/reviews`, {
    method: 'POST', body: JSON.stringify(payload)
  })
