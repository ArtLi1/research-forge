<script setup lang="ts">
import { ElButton, ElMessage, ElProgress } from 'element-plus'
import { ref } from 'vue'

import { retryTask } from '@/api'
import { useTaskProgress } from '@/composables/useTaskProgress'

const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{ completed: [] }>()
const { task, activeTaskId, disconnected, followTask } = useTaskProgress(
  () => props.taskId, () => emit('completed'),
)
const retrying = ref(false)

async function retry() {
  retrying.value = true
  const retriedId = activeTaskId.value
  try {
    const replacement = await retryTask(retriedId)
    if (activeTaskId.value !== retriedId) return
    followTask(replacement.id, replacement)
    ElMessage.success('重试任务已提交')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务重试失败')
  } finally {
    retrying.value = false
  }
}

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
    <p v-if="disconnected" class="error-copy">进度连接中断，正在重新连接…</p>
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
