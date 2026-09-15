import axios from 'axios'

export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.error?.message ?? error.message ?? '请求失败'
    return Promise.reject(new Error(message))
  },
)
