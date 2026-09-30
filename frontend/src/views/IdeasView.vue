<script setup lang="ts">
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElMessage, ElMessageBox, ElOption, ElSelect, ElTag } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { createIdea, deleteIdea, evaluateIdea, getIdeas, getProject, updateIdea } from '@/api'
import type { Project, UserIdea } from '@/types'

const route = useRoute()
const projectId = String(route.params.id)
const project = ref<Project | null>(null)
const ideas = ref<UserIdea[]>([])
const saving = ref(false)
const evaluatingId = ref('')
const editorOpen = ref(false)
const editingId = ref('')
const form = reactive({
  title: '',
  content: '',
  idea_type: 'other',
  status: 'draft',
  tags: [] as string[],
})

const title = computed(() => (editingId.value ? '编辑想法' : '记录新想法'))
const statusLabels: Record<string, string> = {
  draft: '草稿',
  to_verify: '待验证',
  partially_feasible: '部分可行',
  adopted: '已采纳',
  abandoned: '已放弃',
}

async function load() {
  ;[project.value, ideas.value] = await Promise.all([getProject(projectId), getIdeas(projectId)])
}

function openEditor(idea?: UserIdea) {
  editingId.value = idea?.id ?? ''
  form.title = idea?.title ?? ''
  form.content = idea?.content ?? ''
  form.idea_type = idea?.idea_type ?? 'other'
  form.status = idea?.status ?? 'draft'
  form.tags = [...(idea?.tags ?? [])]
  editorOpen.value = true
}

async function save() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  saving.value = true
  try {
    const payload = {
      title: form.title,
      content: form.content,
      idea_type: form.idea_type,
      status: form.status,
      tags: form.tags,
    }
    if (editingId.value) await updateIdea(editingId.value, payload)
    else await createIdea(projectId, payload)
    editorOpen.value = false
    ElMessage.success('想法已保存')
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(idea: UserIdea) {
  await ElMessageBox.confirm(`删除“${idea.title}”？`, '确认删除', { type: 'warning' })
  await deleteIdea(idea.id)
  ElMessage.success('想法已删除')
  await load()
}

async function evaluate(idea: UserIdea) {
  evaluatingId.value = idea.id
  try {
    await evaluateIdea(idea.id)
    ElMessage.success('Agent 评估已完成')
    await load()
  } finally {
    evaluatingId.value = ''
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="page-actions reveal">
    <div>
      <p class="section-kicker">Idea Workspace</p>
      <h2>{{ project?.name || '项目' }} · 个人想法</h2>
      <p class="page-intro">保存尚未证实的判断，并让 Agent 基于项目知识检查可行性与证据缺口。</p>
    </div>
    <el-button type="primary" size="large" @click="openEditor()">记录想法</el-button>
  </section>

  <section v-if="ideas.length" class="idea-grid reveal delay-1">
    <article v-for="idea in ideas" :key="idea.id" class="idea-card">
      <header>
        <div>
          <p class="section-kicker">{{ idea.idea_type }}</p>
          <h3>{{ idea.title }}</h3>
        </div>
        <el-tag>{{ statusLabels[idea.status] ?? idea.status }}</el-tag>
      </header>
      <p class="idea-content">{{ idea.content }}</p>
      <div v-if="idea.tags.length" class="tag-row">
        <el-tag v-for="tag in idea.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
      </div>
      <section v-if="idea.agent_evaluation" class="idea-evaluation">
        <strong>Agent 评估</strong>
        <p>{{ idea.agent_evaluation.rationale }}</p>
        <small>
          建议 {{ idea.agent_evaluation.recommendation }} ·
          复杂度 {{ idea.agent_evaluation.complexity_assessment }}
        </small>
      </section>
      <footer>
        <el-button text @click="openEditor(idea)">编辑</el-button>
        <el-button
          text
          :loading="evaluatingId === idea.id"
          @click="evaluate(idea)"
        >
          Agent 评估
        </el-button>
        <el-button text type="danger" @click="remove(idea)">删除</el-button>
      </footer>
    </article>
  </section>
  <EmptyState
    v-else
    class="reveal delay-1"
    title="还没有个人想法"
    description="记录一个假设、算法方向或待验证问题。"
  />

  <el-dialog v-model="editorOpen" :title="title" width="min(620px, 92vw)">
    <el-form label-position="top">
      <el-form-item label="标题">
        <el-input v-model="form.title" maxlength="500" />
      </el-form-item>
      <el-form-item label="内容">
        <el-input v-model="form.content" type="textarea" :rows="6" />
      </el-form-item>
      <div class="idea-form-row">
        <el-form-item label="类型">
          <el-select v-model="form.idea_type">
            <el-option label="场景" value="scenario" />
            <el-option label="模型" value="model" />
            <el-option label="算法" value="algorithm" />
            <el-option label="创新点" value="innovation" />
            <el-option label="假设" value="hypothesis" />
            <el-option label="问题" value="question" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
      </div>
      <el-form-item label="标签">
        <el-select v-model="form.tags" multiple filterable allow-create default-first-option />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editorOpen = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>
