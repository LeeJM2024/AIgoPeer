import { apiFetch } from '../client'

export const getProgrammingProblem = (assignmentId) =>
  apiFetch(`/api/student/assignments/${assignmentId}/programming-problem`)

export const submitCode = (assignmentId, sourceCode) =>
  apiFetch(`/api/assignments/${assignmentId}/code-submissions`, {
    method: 'POST',
    body: JSON.stringify({ language: 'cpp17', source_code: sourceCode })
  })

export const getCodeSubmission = (submissionId) =>
  apiFetch(`/api/code-submissions/${submissionId}`)

export const getCodeSubmissionHistory = (assignmentId, page = 1, pageSize = 5) =>
  apiFetch(`/api/student/assignments/${assignmentId}/code-submissions?page=${page}&page_size=${pageSize}`)
