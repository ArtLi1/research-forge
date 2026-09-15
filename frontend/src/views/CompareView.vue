<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import { comparePapers, getPapers } from '@/api'
import type { ComparisonResult, Paper } from '@/types'

const papers = ref<Paper[]>([])
const selected = ref<string[]>([])
const result = ref<ComparisonResult | null>(null)
const loading = ref(false)
const paperMap = computed(() => new Map(papers.value.map((paper) => [paper.id, paper])))

onMounted(async () => {
  papers.value = await getPapers(true)
})

async function compare() {
  if (selected.value.length < 2 || selected.value.length > 5) {
    ElMessage.warning('请选择 2 至 5 篇已有知识卡的论文')
    return
  }
  loading.value = true
  try {
    result.value = await comparePapers(selected.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '结构化比较失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="compare-stage reveal">
    <div>
      <p class="section-kicker">Structured Comparison</p>
      <h2>比较论文中的场景与算法启发。</h2>
      <p>比较只读取已保存的启发知识卡，不重新阅读全文。</p>
    </div>
    <div class="compare-picker">
      <el-select
        v-model="selected"
        multiple
        filterable
        collapse-tags
        placeholder="选择 2 至 5 篇知识卡已就绪的论文"
      >
        <el-option
          v-for="paper in papers"
          :key="paper.id"
          :label="paper.title"
          :value="paper.id"
        />
      </el-select>
      <el-button type="primary" size="large" :loading="loading" @click="compare">
        生成结构化比较
      </el-button>
      <small>当前有 {{ papers.length }} 篇论文可比较</small>
    </div>
  </section>

  <section v-if="result" class="comparison-sheet reveal">
    <header>
      <p class="section-kicker">Comparison Summary</p>
      <h2>{{ result.summary }}</h2>
    </header>
    <article v-for="dimension in result.dimensions" :key="dimension.dimension">
      <div class="comparison-dimension">
        <h3>{{ dimension.dimension }}</h3>
        <el-tag effect="plain">{{ dimension.conclusion_type }}</el-tag>
      </div>
      <div class="comparison-entries">
        <div v-for="entry in dimension.entries" :key="entry.paper_id">
          <small>{{ paperMap.get(entry.paper_id)?.title || entry.paper_id }}</small>
          <p>{{ entry.statement }}</p>
        </div>
      </div>
      <footer>{{ dimension.conclusion }}</footer>
    </article>
  </section>
  <EmptyState
    v-else
    title="等待选择论文"
    description="固定比较应用场景、算法思路、核心机制、创新差异与适用条件。"
  />
</template>
