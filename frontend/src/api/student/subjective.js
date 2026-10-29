import { apiFetch } from '../client'

export const getSubjective = (id) => apiFetch(`/api/student/assignments/${id}/subjective`)
export const submitSubjective = (id, content) => apiFetch(`/api/student/assignments/${id}/subjective-submissions`, {
  method: 'POST', body: JSON.stringify({ content })
})
export const getSubjectiveHistory = (id, page = 1) => apiFetch(`/api/student/assignments/${id}/subjective-submissions/mine?page=${page}`)
