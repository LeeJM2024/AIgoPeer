import { apiFetch } from '../client'

export const getMyPublishedGrade = (assignmentId) =>
  apiFetch(`/api/student/grades?assignment_id=${encodeURIComponent(assignmentId)}`)
