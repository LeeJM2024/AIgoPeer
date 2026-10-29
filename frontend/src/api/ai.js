import { apiFetch } from './client'

export const getTextAiSettings = () => apiFetch('/api/teacher/ai-text/settings')
export const saveTextAiSettings = (payload) => apiFetch('/api/teacher/ai-text/settings', { method: 'PUT', body: JSON.stringify(payload) })
export const testTextAiSettings = (payload) => apiFetch('/api/teacher/ai-text/test', { method: 'POST', body: JSON.stringify(payload) })
export const deleteTextAiSettings = () => apiFetch('/api/teacher/ai-text/settings', { method: 'DELETE' })
export const getStudentAiStatus = () => apiFetch('/api/student/ai/status')
export const getAiTopics = () => apiFetch('/api/student/ai/topics')
function address(mode, id, action) {
  if (mode === 'PROGRAMMING') return `/api/student/assignments/${id}/ai/${action}`
  if (mode === 'KNOWLEDGE') return `/api/student/ai/topics/${id}/${action}`
  return `/api/teacher/ai/teaching/${action}${id ? '?class_id=' + encodeURIComponent(id) : ''}`
}
export const getAiHistory = (mode, id) => apiFetch(address(mode, id, 'history'))
export const askAi = (mode, id, payload) => apiFetch(address(mode, id, 'messages'), { method: 'POST', body: JSON.stringify(payload) })
