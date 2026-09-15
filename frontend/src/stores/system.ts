import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getHealth } from '@/api'
import type { HealthResponse } from '@/types'

export const useSystemStore = defineStore('system', () => {
  const health = ref<HealthResponse | null>(null)
  const loading = ref(false)

  async function refreshHealth() {
    loading.value = true
    try {
      health.value = await getHealth()
    } finally {
      loading.value = false
    }
  }

  return { health, loading, refreshHealth }
})
