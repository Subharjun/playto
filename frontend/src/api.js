import axios from 'axios'

// The Vite dev server proxies /api to http://localhost:8000
// In production, set VITE_API_BASE_URL env var to the backend URL
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach auth token from localStorage to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken')
  if (token) {
    config.headers.Authorization = `Token ${token}`
  }
  return config
})

export const signup = (email, password, company_name, bank_account_id) => 
  api.post('/api/v1/merchants/signup/', { email, password, company_name, bank_account_id })

export const login = (email, password) => api.post('/api/v1/merchants/login/', { email, password })

export const getMerchantProfile = () => api.get('/api/v1/merchants/me/')

export const getPayouts = () => api.get('/api/v1/payouts/')

export const getPayout = (id) => api.get(`/api/v1/payouts/${id}/`)

export const createPayout = (data, idempotencyKey) =>
  api.post('/api/v1/payouts/', data, {
    headers: { 'Idempotency-Key': idempotencyKey },
  })

export const getLedger = () => api.get('/api/v1/ledger/')

export default api
