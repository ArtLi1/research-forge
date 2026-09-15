<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import { getPapers, getProjects, uploadPapers } from '@/api'
import type { Paper, Project } from '@/types'
import { statusLabel, statusTone } from '@/utils/status'

const route = useRoute()
const papers = ref<Paper[]>([])
const projects = ref<Project[]>([])
const files = ref<File[]>([])
const projectId = ref(String(route.query.project ?? ''))
const uploading = ref(false)
const activeTasks = ref<string[]>([])
const completedCount = computed(
  () => papers.value.filter((paper) => ['completed', 'partial'].includes(paper.parse_status)).length,
)

async function load() {
  ;[papers.value, projects.value] = await Promise.all([getPapers(), getProjects()])
}

function chooseFiles(event: Event) {
  files.value = Array.from((event.target as HTMLInputElement).files ?? [])
}

async function upload() {
  if (!files.value.length) return
  uploading.value = true
  try {
    const results = await uploadPapers(files.value, projectId.value || undefined)
    activeTasks.value.push(
      ...results.flatMap((result) => (result.task_id ? [result.task_id] : [])),
    )
    const duplicateCount = results.filter((result) => result.duplicate).length
    ElMessage.success(
      duplicateCount ? `上传完成，${duplicateCount} 篇命中全局去重` : '上传完成，已进入解析队列',
    )
    files.value = []
    await load()
  } finally {
    uploading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="library-stats reveal">
    <div><strong>{{ papers.length }}</strong><span>全局论文</span></div>
    <div><strong>{{ completedCount }}</strong><span>可检索</span></div>
    <div><strong>{{ activeTasks.length }}</strong><span>本页任务</span></div>
  </section>

  <section class="upload-panel reveal delay-1">
    <div>
      <p class="section-kicker">PDF 导入</p>
      <h2>把原文交给知识流水线</h2>
      <p>支持文本型 PDF；系统按 SHA-256 全局去重，并在后台解析、分块和向量化。</p>
    </div>
    <div class="upload-controls">
      <label class="file-drop">
        <input type="file" accept=".pdf,application/pdf" multiple @change="chooseFiles" />
        <span>{{ files.length ? `已选择 ${files.length} 个文件` : '选择或拖入 PDF' }}</span>
        <small>单文件最大 50 MB</small>
      </label>
      <el-select v-model="projectId" clearable placeholder="可选：同时加入项目">
        <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
      </el-select>
      <el-button type="primary" size="large" :loading="uploading" :disabled="!files.length" @click="upload">
        上传并处理
      </el-button>
    </div>
  </section>

  <section v-if="activeTasks.length" class="task-stack reveal">
    <TaskProgress
      v-for="taskId in activeTasks"
      :key="taskId"
      :task-id="taskId"
      @completed="load"
    />
  </section>

  <section class="content-panel reveal delay-2">
    <div class="panel-heading">
      <div>
        <p class="section-kicker">Global Library</p>
        <h2>全局文献库</h2>
      </div>
      <router-link to="/compare">选择论文进行对比 →</router-link>
    </div>
    <el-table v-if="papers.length" :data="papers" class="paper-table">
      <el-table-column label="论文标题" min-width="380">
        <template #default="{ row }">
          <router-link class="table-link" :to="`/papers/${row.id}`">{{ row.title }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="year" label="年份" width="90" />
      <el-table-column prop="source_type" label="来源" width="100" />
      <el-table-column label="处理状态" width="130">
        <template #default="{ row }">
          <el-tooltip v-if="row.parse_error" :content="row.parse_error">
            <el-tag :type="statusTone(row.parse_status)">{{ statusLabel[row.parse_status] }}</el-tag>
          </el-tooltip>
          <el-tag v-else :type="statusTone(row.parse_status)">
            {{ statusLabel[row.parse_status] ?? row.parse_status }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
    <EmptyState
      v-else
      title="文献库尚为空"
      description="上传第一篇 PDF，建立可跨项目复用的全局文献资产。"
    />
  </section>
</template>
