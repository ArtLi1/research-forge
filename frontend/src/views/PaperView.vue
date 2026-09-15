<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import KnowledgeCard from '@/components/KnowledgeCard.vue'
import MetadataEditor from '@/components/MetadataEditor.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import {
  createMetadataDefinition,
  extractKnowledge,
  getKnowledge,
  getMetadataDefinitions,
  getPaper,
} from '@/api'
import type { KnowledgeCard as KnowledgeCardType, MetadataDefinition, Paper } from '@/types'

const route = useRoute()
const paper = ref<Paper | null>(null)
const card = ref<KnowledgeCardType | null>(null)
const definitions = ref<MetadataDefinition[]>([])
const loading = ref(true)
const taskId = ref('')
const definitionDialog = ref(false)
const definitionForm = reactive({
  name: '',
  description: '',
  value_type: 'text',
  optionsText: '',
  auto_extract: true,
})
const globalDefinitions = computed(() =>
  definitions.value.filter((item) => item.scope === 'global_paper'),
)

async function load() {
  loading.value = true
  const id = String(route.params.id)
  try {
    ;[paper.value, definitions.value] = await Promise.all([
      getPaper(id),
      getMetadataDefinitions(),
    ])
    try {
      card.value = await getKnowledge(id)
    } catch {
      card.value = null
    }
  } finally {
    loading.value = false
  }
}

async function startExtraction() {
  const task = await extractKnowledge(String(route.params.id))
  taskId.value = task.id
  ElMessage.success('知识提取任务已提交')
}

async function createDefinition() {
  const enumType = ['single_enum', 'multi_enum'].includes(definitionForm.value_type)
  await createMetadataDefinition({
    name: definitionForm.name,
    description: definitionForm.description,
    scope: 'global_paper',
    value_type: definitionForm.value_type as MetadataDefinition['value_type'],
    options: enumType
      ? definitionForm.optionsText
          .split('\n')
          .map((item) => item.trim())
          .filter(Boolean)
      : undefined,
    auto_extract: definitionForm.auto_extract,
  })
  definitionDialog.value = false
  Object.assign(definitionForm, {
    name: '',
    description: '',
    value_type: 'text',
    optionsText: '',
    auto_extract: true,
  })
  await load()
}

onMounted(() => void load())
</script>

<template>
  <div v-loading="loading">
    <section v-if="paper" class="paper-hero reveal">
      <div>
        <p class="section-kicker">Global Paper · {{ paper.source_type }}</p>
        <h2>{{ paper.title }}</h2>
        <p>
          {{ paper.authors.join(' · ') || '作者信息待补充' }}
          <span v-if="paper.year"> · {{ paper.year }}</span>
        </p>
      </div>
      <dl>
        <dt>处理状态</dt>
        <dd>{{ paper.parse_status }}</dd>
        <dt>DOI / arXiv</dt>
        <dd>{{ paper.doi || paper.arxiv_id || '未记录' }}</dd>
      </dl>
    </section>

    <TaskProgress
      v-if="taskId"
      :task-id="taskId"
      class="reveal"
      @completed="taskId = ''; load()"
    />

    <KnowledgeCard v-if="card" :card="card" class="reveal delay-1" />
    <section v-else-if="paper" class="knowledge-empty reveal delay-1">
      <p class="section-kicker">Knowledge Extraction</p>
      <h2>正文已准备，知识卡尚未生成。</h2>
      <p>系统将提取可迁移的研究场景、核心挑战、算法思路与关键机制。</p>
      <el-button type="primary" size="large" @click="startExtraction">开始提取知识卡</el-button>
    </section>

    <section v-if="paper" class="content-panel reveal delay-2">
      <div class="panel-heading">
        <div>
          <p class="section-kicker">Custom Metadata</p>
          <h2>全局论文元数据</h2>
        </div>
        <el-button @click="definitionDialog = true">新建字段</el-button>
      </div>
      <MetadataEditor
        :paper="paper"
        :definitions="globalDefinitions"
        @refresh="load"
      />
    </section>
  </div>

  <el-dialog v-model="definitionDialog" title="创建全局论文字段" width="min(560px, 92vw)">
    <el-form label-position="top">
      <el-form-item label="字段名称" required>
        <el-input v-model="definitionForm.name" />
      </el-form-item>
      <el-form-item label="填写标准">
        <el-input v-model="definitionForm.description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="值类型">
        <el-select v-model="definitionForm.value_type">
          <el-option label="文本" value="text" />
          <el-option label="布尔值" value="boolean" />
          <el-option label="单选枚举" value="single_enum" />
          <el-option label="多选枚举" value="multi_enum" />
          <el-option label="1–5 评分" value="rating" />
        </el-select>
      </el-form-item>
      <el-form-item
        v-if="['single_enum', 'multi_enum'].includes(definitionForm.value_type)"
        label="枚举选项（每行一项）"
      >
        <el-input v-model="definitionForm.optionsText" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="允许 Agent 自动填充">
        <el-switch v-model="definitionForm.auto_extract" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="definitionDialog = false">取消</el-button>
      <el-button type="primary" :disabled="!definitionForm.name" @click="createDefinition">
        创建字段
      </el-button>
    </template>
  </el-dialog>
</template>
