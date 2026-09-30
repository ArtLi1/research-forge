<script setup lang="ts">
import { ElButton, ElMessage, ElMessageBox, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { getProject, getProjectKnowledge, getProjectPapers, removeProjectPaper } from '@/api'
import type { Paper, Project, ProjectKnowledge } from '@/types'
import { statusLabel, statusTone } from '@/utils/status'

const route = useRoute()
const project = ref<Project | null>(null)
const papers = ref<Paper[]>([])
const knowledge = ref<ProjectKnowledge[]>([])
const removingPaperId = ref('')

const categoryLabels: Record<string, string> = {
  common_scenarios: '共性场景',
  system_mechanisms: '系统机制',
  algorithm_routes: '算法路线',
  innovation_patterns: '创新模式',
  limitations_risks: '局限与风险',
  research_opportunities: '研究机会',
  confirmed_schemes: '已确认方案',
}

async function load() {
  const id = String(route.params.id)
  ;[project.value, papers.value, knowledge.value] = await Promise.all([
    getProject(id),
    getProjectPapers(id),
    getProjectKnowledge(id),
  ])
}

async function removePaper(paperId: string, title: string) {
  try {
    await ElMessageBox.confirm(
      `从当前项目移除“${title}”？全局文献和知识卡不会删除。`,
      '移除项目文献',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  removingPaperId.value = paperId
  try {
    await removeProjectPaper(String(route.params.id), paperId)
    ElMessage.success('已从项目移除，论文仍保留在全局文献库')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '移除项目文献失败')
  } finally {
    removingPaperId.value = ''
  }
}

onMounted(() => void load())
</script>

<template>
  <section v-if="project" class="project-hero reveal">
    <div>
      <p class="section-kicker">研究方向</p>
      <h2>{{ project.name }}</h2>
      <p>{{ project.description }}</p>
    </div>
    <dl>
      <dt>研究目标</dt>
      <dd>{{ project.research_goal || '待定义' }}</dd>
      <dt>排除项</dt>
      <dd>{{ project.exclusions.join(' · ') || '无' }}</dd>
    </dl>
  </section>

  <section class="content-panel reveal delay-1">
    <div class="panel-heading">
      <div>
        <p class="section-kicker">Project Knowledge</p>
        <h2>项目知识库 · {{ knowledge.length }} 个类别</h2>
      </div>
      <div class="panel-links">
        <router-link :to="`/projects/${route.params.id}/ideas`">管理个人想法</router-link>
        <router-link :to="`/projects/${route.params.id}/schemes`">研究构思工作台 →</router-link>
      </div>
    </div>
    <div v-if="knowledge.length" class="project-knowledge-grid">
      <article v-for="group in knowledge" :key="group.id" class="project-knowledge-panel">
        <header>
          <h3>{{ categoryLabels[group.category] ?? group.category }}</h3>
          <span>v{{ group.version_number }}</span>
        </header>
        <ul>
          <li v-for="(item, index) in group.content.items" :key="`${item.source_id}-${index}`">
            <p>{{ item.statement }}</p>
            <small>
              {{ item.source_type === 'paper' ? '论文' : item.source_type === 'user_idea' ? '个人想法' : '已确认方案' }}
              · {{ item.source_id.slice(0, 8) }}
            </small>
          </li>
        </ul>
        <footer>{{ group.change_summary }}</footer>
      </article>
    </div>
    <EmptyState
      v-else
      title="项目知识尚未形成"
      description="论文知识卡提取完成后，系统会增量归并到项目知识库。"
    />
  </section>

  <section class="content-panel reveal delay-2">
    <div class="panel-heading">
      <div>
        <p class="section-kicker">项目文献范围</p>
        <h2>{{ papers.length }} 篇已关联论文</h2>
      </div>
      <router-link :to="{ path: '/library', query: { project: route.params.id } }">
        上传并关联论文 →
      </router-link>
    </div>
    <el-table v-if="papers.length" :data="papers" class="paper-table">
      <el-table-column label="论文" min-width="360">
        <template #default="{ row }">
          <router-link class="table-link" :to="`/papers/${row.id}`">{{ row.title }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="year" label="年份" width="90" />
      <el-table-column label="处理状态" width="130">
        <template #default="{ row }">
          <el-tag :type="statusTone(row.parse_status)">
            {{ statusLabel[row.parse_status] ?? row.parse_status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="right">
        <template #default="{ row }">
          <el-button
            text
            type="danger"
            :loading="removingPaperId === row.id"
            @click="removePaper(row.id, row.title)"
          >
            移除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <EmptyState
      v-else
      title="项目范围还是空的"
      description="上传论文时选择当前项目，或从全局文献库关联已有论文。"
    />
  </section>
</template>
