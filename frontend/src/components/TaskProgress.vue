<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { retryTask } from '@/api'
import type { BackgroundTask } from '@/types'

const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{ completed: [] }>()
const task = ref<BackgroundTask | null>(null)
const activeTaskId = ref(props.taskId)
const retrying = ref(false)
let source: EventSource | null = null

function receive(event: MessageEvent) {
  task.value = JSON.parse(event.data) as BackgroundTask
}

function connect(taskId: string) {
  source?.close()
  source = new EventSource(`/api/v1/tasks/${taskId}/events`)
  source.addEventListener('progress', receive)
  source.addEventListener('completed', (event) => {
    receive(event)
    source?.close()
    emit('completed')
  })
  source.addEventListener('failed', (event) => {
    receive(event)
    source?.close()
  })
}

async function retry() {
  retrying.value = true
  try {
    const replacement = await retryTask(activeTaskId.value)
    activeTaskId.value = replacement.id
    task.value = replacement
    connect(replacement.id)
    ElMessage.success('重试任务已提交')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务重试失败')
  } finally {
    retrying.value = false
  }
}

onMounted(() => {
  connect(activeTaskId.value)
})

onBeforeUnmount(() => source?.close())
</script>

<template>
  <div class="task-progress">
    <div class="task-progress__label">
      <span>{{ task?.message ?? '正在连接任务…' }}</span>
      <strong>{{ task?.progress ?? 0 }}%</strong>
    </div>
    <el-progress
      :percentage="task?.progress ?? 0"
      :status="task?.status === 'failed' ? 'exception' : task?.progress === 100 ? 'success' : undefined"
      :show-text="false"
    />
    <p v-if="task?.error" class="error-copy">{{ task.error }}</p>
    <el-button
      v-if="task?.status === 'failed'"
      type="danger"
      plain
      size="small"
      :loading="retrying"
      @click="retry"
    >
      重试任务
    </el-button>
  </div>
</template>
