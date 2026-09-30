<script setup lang="ts">
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElLoading, ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import { createProject, deleteProject, getProjects } from '@/api'
import type { Project } from '@/types'

const vLoading = ElLoading.directive
const projects = ref<Project[]>([])
const loading = ref(false)
const dialogOpen = ref(false)
const form = reactive({
  name: '',
  description: '',
  research_goal: '',
  exclusionsText: '',
})

async function load() {
  loading.value = true
  try {
    projects.value = await getProjects()
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.name.trim()) return
  await createProject({
    name: form.name,
    description: form.description,
    research_goal: form.research_goal,
    preferences: {},
    exclusions: form.exclusionsText
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean),
  })
  dialogOpen.value = false
  Object.assign(form, { name: '', description: '', research_goal: '', exclusionsText: '' })
  ElMessage.success('项目已创建')
  await load()
}

async function remove(project: Project) {
  await ElMessageBox.confirm(`删除项目“${project.name}”？全局论文不会被删除。`, '确认删除', {
    type: 'warning',
  })
  await deleteProject(project.id)
  await load()
}

onMounted(() => void load())
</script>

<template>
  <div class="page-actions reveal">
    <div>
      <p class="section-kicker">单层研究方向</p>
      <p class="page-intro">每个项目建立独立论文范围，同一篇论文可被多个项目复用。</p>
    </div>
    <el-button type="primary" size="large" @click="dialogOpen = true">新建研究项目</el-button>
  </div>

  <div v-loading="loading" class="project-grid reveal delay-1">
    <article v-for="(project, index) in projects" :key="project.id" class="project-card">
      <div class="project-card__index">{{ String(index + 1).padStart(2, '0') }}</div>
      <p class="project-card__date">
        {{ new Date(project.updated_at).toLocaleDateString('zh-CN') }}
      </p>
      <h2>{{ project.name }}</h2>
      <p>{{ project.description || '尚未填写研究方向说明。' }}</p>
      <div class="project-card__goal">
        <small>研究目标</small>
        <span>{{ project.research_goal || '待定义' }}</span>
      </div>
      <footer>
        <router-link :to="`/projects/${project.id}`">打开工作台 →</router-link>
        <el-button link type="danger" @click="remove(project)">删除</el-button>
      </footer>
    </article>
    <EmptyState
      v-if="!loading && projects.length === 0"
      title="还没有研究项目"
      description="先建立一个研究方向，再将全局论文关联进来。"
    >
      <el-button type="primary" @click="dialogOpen = true">创建第一个项目</el-button>
    </EmptyState>
  </div>

  <el-dialog v-model="dialogOpen" title="建立研究方向" width="min(620px, 92vw)">
    <el-form label-position="top">
      <el-form-item label="项目名称" required>
        <el-input v-model="form.name" placeholder="例如：灾后 UAV-RSU 语义计算卸载" />
      </el-form-item>
      <el-form-item label="方向说明">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="当前研究目标">
        <el-input v-model="form.research_goal" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="明确排除项（每行一项）">
        <el-input v-model="form.exclusionsText" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogOpen = false">取消</el-button>
      <el-button type="primary" @click="submit">创建项目</el-button>
    </template>
  </el-dialog>
</template>
