<script setup lang="ts">
import { ElButton, ElInput, ElMessage, ElOption, ElSelect } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import CandidateSchemeCard from '@/components/CandidateSchemeCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import { generateSchemes, getIdeas, getProject, getSchemes } from '@/api'
import type { CandidateScheme, Project, UserIdea } from '@/types'

const route = useRoute()
const projectId = String(route.params.id)
const project = ref<Project | null>(null)
const ideas = ref<UserIdea[]>([])
const schemes = ref<CandidateScheme[]>([])
const goal = ref('')
const selectedIdeaIds = ref<string[]>([])
const taskId = ref('')
const submitting = ref(false)

async function load() {
  ;[project.value, ideas.value, schemes.value] = await Promise.all([
    getProject(projectId),
    getIdeas(projectId),
    getSchemes(projectId),
  ])
  if (!goal.value) goal.value = project.value.research_goal || ''
}

async function generate() {
  if (goal.value.trim().length < 5) {
    ElMessage.warning('请填写至少 5 个字符的研究目标')
    return
  }
  submitting.value = true
  try {
    const task = await generateSchemes(projectId, {
      goal: goal.value,
      selected_idea_ids: selectedIdeaIds.value,
      candidate_count: 3,
    })
    taskId.value = task.id
    ElMessage.success('LangGraph 构思任务已提交')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '候选方案生成失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="scheme-studio reveal">
    <div>
      <p class="section-kicker">Research Graph Studio</p>
      <h2>从宽泛目标分叉出三条研究路线。</h2>
      <p>
        LangGraph 将项目知识、文献证据与个人想法汇集后，检查差异性、证据、兼容性和风险。
      </p>
    </div>
    <div class="scheme-brief">
      <label>
        <span>本轮研究目标</span>
        <el-input v-model="goal" type="textarea" :rows="5" maxlength="4000" show-word-limit />
      </label>
      <label>
        <span>参与构思的个人想法（可选）</span>
        <el-select v-model="selectedIdeaIds" multiple filterable clearable>
          <el-option
            v-for="idea in ideas"
            :key="idea.id"
            :label="idea.title"
            :value="idea.id"
          />
        </el-select>
      </label>
      <el-button type="primary" size="large" :loading="submitting" @click="generate">
        生成三个候选方案
      </el-button>
      <small>论文内容会发送到当前配置的第三方模型服务。</small>
    </div>
  </section>

  <TaskProgress
    v-if="taskId"
    :task-id="taskId"
    class="reveal"
    @completed="taskId = ''; load()"
  />

  <section v-if="schemes.length" class="scheme-results reveal delay-1">
    <div class="panel-heading">
      <div>
        <p class="section-kicker">Candidate Branches</p>
        <h2>{{ schemes.length }} 个候选分支</h2>
      </div>
    </div>
    <div class="scheme-grid">
      <CandidateSchemeCard
        v-for="(scheme, index) in schemes"
        :key="scheme.id"
        :scheme="scheme"
        :index="index"
      />
    </div>
  </section>
  <EmptyState
    v-else
    class="reveal delay-1"
    title="等待第一次研究构思"
    description="提交目标后，系统会生成三个结构明显不同且带证据与风险的候选方案。"
  />
</template>
