<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import { getProjects, searchPapers } from '@/api'
import type { EvidencePack, Project } from '@/types'

const projects = ref<Project[]>([])
const query = ref('')
const scope = ref<'global' | 'project'>('project')
const projectId = ref('')
const loading = ref(false)
const result = ref<EvidencePack | null>(null)

onMounted(async () => {
  projects.value = await getProjects()
  projectId.value = projects.value[0]?.id ?? ''
})

async function submit() {
  if (!query.value.trim()) return
  if (scope.value === 'project' && !projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    result.value = await searchPapers({
      query: query.value,
      scope: scope.value,
      project_id: scope.value === 'project' ? projectId.value : undefined,
      top_k: 12,
    })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="search-stage reveal">
    <p class="section-kicker">Evidence Retrieval</p>
    <h2>从原文证据，而不是印象中检索。</h2>
    <div class="search-box">
      <el-input
        v-model="query"
        size="large"
        placeholder="例如：哪些多跳路径机制适合灾后计算卸载？"
        @keyup.enter="submit"
      />
      <el-button type="primary" size="large" :loading="loading" @click="submit">检索证据</el-button>
    </div>
    <div class="search-scope">
      <el-radio-group v-model="scope">
        <el-radio-button value="project">项目范围</el-radio-button>
        <el-radio-button value="global">全局文献</el-radio-button>
      </el-radio-group>
      <el-select v-if="scope === 'project'" v-model="projectId" placeholder="选择项目">
        <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
      </el-select>
    </div>
  </section>

  <section v-if="result" class="search-results reveal">
    <div class="panel-heading">
      <div>
        <p class="section-kicker">Evidence Pack</p>
        <h2>{{ result.items.length }} 条原文证据</h2>
      </div>
      <span class="query-echo">“{{ result.query }}”</span>
    </div>
    <article v-for="(item, index) in result.items" :key="`${item.paper_id}-${index}`" class="evidence-card">
      <div class="evidence-card__score">{{ Math.round(item.score * 100) }}</div>
      <div>
        <p class="evidence-meta">
          {{ item.paper_title }} · {{ item.year ?? '年份未知' }} ·
          {{ item.section || '未识别章节' }} · P{{ item.page_start }}
        </p>
        <p class="evidence-content">{{ item.content }}</p>
      </div>
    </article>
    <EmptyState
      v-if="result.items.length === 0"
      title="当前范围没有匹配证据"
      :description="result.missing_information.join('；')"
    />
  </section>
</template>
