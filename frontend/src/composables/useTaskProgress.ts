import { onScopeDispose, ref, watch } from 'vue'

import type { BackgroundTask } from '@/types'

export function useTaskProgress(taskId: () => string, completed: () => void) {
  const task = ref<BackgroundTask | null>(null)
  const activeTaskId = ref('')
  const disconnected = ref(false)
  let source: EventSource | null = null

  function close() {
    source?.close()
    source = null
  }

  function followTask(id: string, initial: BackgroundTask | null = null) {
    close()
    activeTaskId.value = id
    task.value = initial
    disconnected.value = false
    if (!id) return
    const connection = new EventSource(`/api/v1/tasks/${id}/events`)
    source = connection
    connection.onopen = () => {
      if (source === connection) disconnected.value = false
    }
    connection.onerror = () => {
      if (source === connection) disconnected.value = true
    }
    const receive = (event: MessageEvent) => {
      if (source !== connection) return
      task.value = JSON.parse(event.data) as BackgroundTask
      disconnected.value = false
    }
    connection.addEventListener('progress', receive)
    for (const name of ['completed', 'failed', 'cancelled']) {
      connection.addEventListener(name, (event) => {
        if (source !== connection) return
        receive(event)
        close()
        if (name === 'completed') completed()
      })
    }
  }

  watch(taskId, (id) => followTask(id), { immediate: true })
  onScopeDispose(close)
  return { task, activeTaskId, disconnected, followTask }
}
