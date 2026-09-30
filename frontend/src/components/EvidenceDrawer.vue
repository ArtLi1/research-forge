<script setup lang="ts">
import { ElDrawer } from 'element-plus'
import { computed } from 'vue'

import type { Evidence, EvidenceRef } from '@/types'

const props = defineProps<{
  modelValue: boolean
  reference: EvidenceRef | null
  evidence: Evidence[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const saved = computed(() =>
  props.evidence.find(
    (item) =>
      item.chunk_id === props.reference?.chunk_id &&
      item.quote.trim() === props.reference?.quote.trim(),
  ),
)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="原文证据"
    size="min(560px, 94vw)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="reference" class="evidence-sheet">
      <p class="section-kicker">Traceable Evidence</p>
      <dl>
        <dt>章节</dt>
        <dd>{{ saved?.section || reference.section || '未识别章节' }}</dd>
        <dt>页码</dt>
        <dd>P{{ saved?.page || reference.page || '—' }}</dd>
        <dt>来源类型</dt>
        <dd>{{ saved?.source_type || 'paper_explicit' }}</dd>
        <dt>置信度</dt>
        <dd>{{ Math.round((saved?.confidence || reference.confidence) * 100) }}%</dd>
      </dl>
      <blockquote>“{{ reference.quote }}”</blockquote>
      <small>Chunk ID · {{ reference.chunk_id }}</small>
    </div>
  </el-drawer>
</template>
