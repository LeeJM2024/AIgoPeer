import { apiFetch } from '../client'

/** Read the unauthenticated backend health endpoint for the development console. */
export const getBackendHealth = () => apiFetch('/api/health')
