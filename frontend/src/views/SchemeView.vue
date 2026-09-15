<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import RiskAssessmentPanel from '@/components/RiskAssessmentPanel.vue'
import { abandonScheme, acceptScheme, getScheme, getSchemeAgentTrace, reviseScheme } from '@/api'
import type { AgentTrace, CandidateScheme } from '@/types'

const route = useRoute()
const scheme = ref<CandidateScheme | null>(null)
const trace = ref<AgentTrace | null>(null)
const revisionOpen = ref(false)
const revisionInstruction = ref('')
const working = ref(false)

const statementFields = [
  ['core_research_question', '核心研究问题'],
  ['scenario_innovation', '场景创新'],
  ['model_level_changes', '模型层变化'],
  ['algorithm_innovation', '算法创新'],
  ['possible_paper_contributions', '可能论文贡献'],
  ['borrowed_mechanisms', '借鉴机制'],
  ['expected_advantages', '预期优势'],
  ['combination_rationale', '组合理由'],
  ['required_assumptions', '必要假设'],
] as const

const stepLabels: Record<string, string> = {
  load_context: '读取项目上下文与用户想法',
  understand_goal: '理解研究目标与硬约束',
  plan_retrieval: '规划场景与算法检索',
  retrieve_knowledge: '检索项目范围内启发知识',
  generate_candidates: '生成三个候选方案',
  validate_candidates: '验证目标、多样性、兼容性与约束',
  assess_risks: '评估方案风险',
  persist_candidates: '保存候选方案与运行轨迹',
}

const current = computed(() => scheme.value?.current_version)
const canAccept = computed(
  () =>
    scheme.value?.status === 'candidate' &&
    !current.value?.risk_assessment.hard_constraint_violations.length,
)

function statements(field: (typeof statementFields)[number][0]): string[] {
  return current.value?.content[field] ?? []
}

async function load() {
  const id = String(route.params.id)
  ;[scheme.value, trace.value] = await Promise.all([
    getScheme(id),
    getSchemeAgentTrace(id).catch(() => null),
  ])
}

async function revise() {
  if (!scheme.value || !revisionInstruction.value.trim()) return
  working.value = true
  try {
    scheme.value = await reviseScheme(
      scheme.value.id,
      revisionInstruction.value,
      scheme.value.current_version_id,
    )
    revisionOpen.value = false
    revisionInstruction.value = ''
    ElMessage.success('已创建新版本')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '方案修改失败')
  } finally {
    working.value = false
  }
}

async function accept() {
  if (!scheme.value) return
  try {
    await ElMessageBox.confirm(
      '接受后，当前版本将写入项目级 confirmed_schemes 知识。旧版本仍会保留。',
      '确认接受当前方案',
      { type: 'warning', confirmButtonText: '明确接受', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  working.value = true
  try {
    scheme.value = await acceptScheme(scheme.value.id, scheme.value.current_version_id)
    ElMessage.success('方案已接受并沉淀到项目知识')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '接受方案失败')
  } finally {
    working.value = false
  }
}

async function abandon() {
  if (!scheme.value) return
  try {
    const result = await ElMessageBox.prompt('请记录放弃原因，历史版本不会删除。', '放弃方案', {
      inputValidator: (value) => value.trim().length >= 2 || '至少填写 2 个字符',
      confirmButtonText: '确认放弃',
      cancelButtonText: '取消',
    })
    working.value = true
    scheme.value = await abandonScheme(scheme.value.id, result.value)
    ElMessage.success('方案已放弃，历史已保留')
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  } finally {
    working.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div v-if="scheme && current">
    <section class="scheme-detail-hero reveal">
      <div>
        <p class="section-kicker">Candidate Scheme · V{{ current.version_number }}</p>
        <h2>{{ scheme.title }}</h2>
        <p>
          {{
            scheme.status === 'candidate'
              ? '候选方案，尚未进入项目确认知识。'
              : scheme.status === 'accepted'
                ? '已由用户明确接受。'
                : '方案已放弃，历史仍保留。'
          }}
        </p>
      </div>
      <div v-if="scheme.status === 'candidate'" class="scheme-detail-actions">
        <el-button @click="revisionOpen = true">填写意见并修改</el-button>
        <el-tooltip :disabled="canAccept" content="存在硬约束违规，必须先修改">
          <span>
            <el-button type="primary" :disabled="!canAccept" :loading="working" @click="accept">
              接受当前版本
            </el-button>
          </span>
        </el-tooltip>
        <el-button type="danger" plain :disabled="working" @click="abandon">放弃</el-button>
      </div>
    </section>

    <div class="scheme-detail-layout reveal delay-1">
      <main class="scheme-manuscript">
        <section v-for="[field, label] in statementFields" :key="field">
          <header>
            <span>{{ label }}</span>
            <small>{{ statements(field).length }}</small>
          </header>
          <article v-for="item in statements(field)" :key="item">
            <p>{{ item }}</p>
          </article>
        </section>
      </main>
      <aside>
        <section v-if="trace" class="version-timeline agent-process">
          <p class="section-kicker">Agent Process</p>
          <p>
            {{ trace.retrieved_scenario_count }} 条场景启发 ·
            {{ trace.retrieved_algorithm_count }} 条算法启发
          </p>
          <article v-for="(step, index) in trace.steps" :key="`${step.name}-${index}`">
            <strong>{{ step.status === 'completed' ? '✓' : '!' }} {{ stepLabels[step.name] || step.name }}</strong>
            <span v-if="step.retry">Feedback-driven retry</span>
            <p v-if="step.issue_count">发现 {{ step.issue_count }} 项验证反馈</p>
          </article>
        </section>
        <RiskAssessmentPanel :risk="current.risk_assessment" />
        <section class="version-timeline">
          <p class="section-kicker">Version Timeline</p>
          <article v-for="version in scheme.versions" :key="version.id">
            <strong>V{{ version.version_number }}</strong>
            <span>{{ new Date(version.created_at).toLocaleString() }}</span>
            <p>{{ version.user_instruction || '初始候选方案' }}</p>
          </article>
        </section>
      </aside>
    </div>
  </div>

  <el-dialog v-model="revisionOpen" title="创建方案新版本" width="min(620px, 92vw)">
    <p class="muted-copy">请具体说明要保留、删除或调整的内容。修改会创建新版本，不覆盖当前历史。</p>
    <el-input
      v-model="revisionInstruction"
      type="textarea"
      :rows="6"
      maxlength="4000"
      show-word-limit
      placeholder="例如：保留多跳灾后场景，但把算法改为无需连续功率控制的分布式启发式路线。"
    />
    <template #footer>
      <el-button @click="revisionOpen = false">取消</el-button>
      <el-button
        type="primary"
        :loading="working"
        :disabled="revisionInstruction.trim().length < 5"
        @click="revise"
      >
        生成新版本
      </el-button>
    </template>
  </el-dialog>
</template>
