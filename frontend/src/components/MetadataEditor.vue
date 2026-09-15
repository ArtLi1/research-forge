<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { reactive, watch } from 'vue'

import { autoFillMetadata, setPaperMetadataValue } from '@/api'
import type { MetadataDefinition, Paper } from '@/types'

const props = defineProps<{ paper: Paper; definitions: MetadataDefinition[] }>()
const emit = defineEmits<{ refresh: [] }>()
const values = reactive<Record<string, unknown>>({})
const filling = reactive<Record<string, boolean>>({})

watch(
  () => [props.paper, props.definitions] as const,
  () => {
    for (const definition of props.definitions) {
      values[definition.id] = props.paper.global_metadata[definition.id] ?? null
    }
  },
  { immediate: true, deep: true },
)

async function save(definition: MetadataDefinition) {
  await setPaperMetadataValue(props.paper.id, definition.id, values[definition.id])
  ElMessage.success(`${definition.name} 已保存`)
  emit('refresh')
}

async function autoFill(definition: MetadataDefinition) {
  filling[definition.id] = true
  try {
    const result = await autoFillMetadata(props.paper.id, definition.id)
    values[definition.id] = result.value
    ElMessage.success(`${definition.name} 已由 Agent 填充`)
    emit('refresh')
  } finally {
    filling[definition.id] = false
  }
}
</script>

<template>
  <div class="metadata-editor">
    <div v-for="definition in definitions" :key="definition.id" class="metadata-row">
      <div>
        <strong>{{ definition.name }}</strong>
        <small>{{ definition.description || definition.value_type }}</small>
      </div>
      <el-switch
        v-if="definition.value_type === 'boolean'"
        :model-value="Boolean(values[definition.id])"
        @update:model-value="values[definition.id] = $event"
      />
      <el-rate
        v-else-if="definition.value_type === 'rating'"
        :model-value="Number(values[definition.id] || 0)"
        @update:model-value="values[definition.id] = $event"
      />
      <el-select
        v-else-if="['single_enum', 'multi_enum'].includes(definition.value_type)"
        :model-value="values[definition.id]"
        :multiple="definition.value_type === 'multi_enum'"
        clearable
        @update:model-value="values[definition.id] = $event"
      >
        <el-option
          v-for="option in definition.options"
          :key="option"
          :label="option"
          :value="option"
        />
      </el-select>
      <el-input
        v-else
        :model-value="String(values[definition.id] ?? '')"
        clearable
        @update:model-value="values[definition.id] = $event"
      />
      <div class="metadata-row__actions">
        <el-button @click="save(definition)">保存</el-button>
        <el-button
          v-if="definition.auto_extract"
          type="primary"
          plain
          :loading="filling[definition.id]"
          @click="autoFill(definition)"
        >
          Agent 填充
        </el-button>
      </div>
    </div>
    <p v-if="!definitions.length" class="muted-copy">尚未创建全局论文自定义字段。</p>
  </div>
</template>
