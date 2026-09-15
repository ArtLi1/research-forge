<script setup lang="ts">
import RiskAssessmentPanel from '@/components/RiskAssessmentPanel.vue'
import type { CandidateScheme } from '@/types'

defineProps<{ scheme: CandidateScheme; index: number }>()

const statusLabels = {
  candidate: '候选',
  accepted: '已接受',
  abandoned: '已放弃',
}
</script>

<template>
  <article class="scheme-card">
    <header>
      <span class="scheme-card__index">0{{ index + 1 }}</span>
      <div>
        <p class="section-kicker">
          V{{ scheme.current_version.version_number }} · {{ statusLabels[scheme.status] }}
        </p>
        <h3>{{ scheme.title }}</h3>
      </div>
      <div class="scheme-score">{{ scheme.current_version.content.recommendation_score }}/5</div>
    </header>
    <div class="scheme-card__question">
      <small>核心研究问题</small>
      <p
        v-for="item in scheme.current_version.content.core_research_question"
        :key="item"
      >
        {{ item }}
      </p>
    </div>
    <dl>
      <dt>场景创新</dt>
      <dd>{{ scheme.current_version.content.scenario_innovation[0] || '待完善' }}</dd>
      <dt>算法创新</dt>
      <dd>{{ scheme.current_version.content.algorithm_innovation[0] || '待完善' }}</dd>
      <dt>实现复杂度</dt>
      <dd>{{ scheme.current_version.content.implementation_complexity }}</dd>
    </dl>
    <RiskAssessmentPanel :risk="scheme.current_version.risk_assessment" />
    <footer>
      <span>{{ scheme.current_version.content.borrowed_mechanisms.length }} 个启发机制</span>
      <router-link :to="`/schemes/${scheme.id}`">查看版本与修改 →</router-link>
    </footer>
  </article>
</template>
