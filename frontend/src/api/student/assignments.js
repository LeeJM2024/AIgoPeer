import { apiFetch } from '../client'

/** Fetch the authenticated student's class-scoped assignment workspace. */
export const getMyAssignments = () => apiFetch('/api/student/assignments')
