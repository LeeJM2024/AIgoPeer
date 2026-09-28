import { apiFetch } from '../client'

export const getAssignmentTopics = (assignmentId) =>
  apiFetch(`/api/student/assignments/${assignmentId}/topics`)

export const claimTopic = (assignmentId, topicId) =>
  apiFetch(`/api/assignments/${assignmentId}/topic-claim`, {
    method: 'POST',
    body: JSON.stringify({ topic_id: topicId })
  })

export const submitProject = (assignmentId, zipFile, manifest) => {
  const formData = new FormData()
  formData.set('zip_file', zipFile)
  formData.set('manifest', JSON.stringify(manifest))
  return apiFetch(`/api/assignments/${assignmentId}/project-submissions`, {
    method: 'POST',
    body: formData
  })
}

export const getMaterialCheck = (submissionId) =>
  apiFetch(`/api/submissions/${submissionId}/material-check`)
