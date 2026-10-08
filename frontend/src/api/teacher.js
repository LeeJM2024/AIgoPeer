import { apiFetch } from './client'

export const getDashboard = () => apiFetch('/api/teacher/dashboard')
export const getClasses = () => apiFetch('/api/teacher/classes')
export const getClassStudents = (id) =>
  apiFetch(`/api/teacher/classes/${id}/students`)
export const getAssignments = () => apiFetch('/api/teacher/assignments')
export const getAssignment = (id) => apiFetch(`/api/teacher/assignments/${id}`)
export const createAssignment = (payload) =>
  apiFetch('/api/teacher/assignments', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const savePanels = (id, panels) =>
  apiFetch(`/api/teacher/assignments/${id}/review-panels`, {
    method: 'PUT',
    body: JSON.stringify({ panels }),
  })
export const publishAssignment = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/publish`, { method: 'POST' })
export const initializeReviewTasks = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/initialize-review-tasks`, {
    method: 'POST',
  })
export const getGradingWorkspace = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/grading`)
export const createTeacherGrade = (submissionId, payload) =>
  apiFetch(`/api/teacher/submissions/${submissionId}/grades`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const correctTeacherGrade = (submissionId, payload) =>
  apiFetch(`/api/teacher/submissions/${submissionId}/grade-corrections`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const lockTeacherGrade = (gradeId) =>
  apiFetch(`/api/teacher/grades/${gradeId}/lock`, { method: 'POST' })
export const createTeacherFinalReview = (submissionId, payload) =>
  apiFetch(`/api/teacher/submissions/${submissionId}/final-review`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const publishResults = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/publish-results`, { method: 'POST' })
export const getAiVideoStatus = () => apiFetch('/api/teacher/ai-video/status')

export const createClass = (payload) =>
  apiFetch('/api/teacher/classes', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const editClass = (id, payload) =>
  apiFetch(`/api/teacher/classes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
export const importStudents = (id, students) =>
  apiFetch(`/api/teacher/classes/${id}/students/import`, {
    method: 'POST',
    body: JSON.stringify({ students }),
  })
export const removeEnrollment = (classId, studentId) =>
  apiFetch(`/api/teacher/classes/${classId}/students/${studentId}`, {
    method: 'DELETE',
  })
export const editAssignment = (id, payload) =>
  apiFetch(`/api/teacher/assignments/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
export const deleteAssignment = (id) =>
  apiFetch(`/api/teacher/assignments/${id}`, { method: 'DELETE' })
export const getAnomalies = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/anomalies`)
export const resolveAnomaly = (id, payload) =>
  apiFetch(`/api/teacher/anomalies/${id}/resolve`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const getReviewProgress = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/review-progress`)
export const extendReviewDeadline = (id, payload) =>
  apiFetch(`/api/teacher/assignments/${id}/review-deadline`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
export const getPublicationReadiness = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/publication-readiness`)
export const getGradeHistory = (id) =>
  apiFetch(`/api/teacher/submissions/${id}/grade-history`)
export const getStatistics = (id) =>
  apiFetch(`/api/teacher/assignments/${id}/statistics`)
