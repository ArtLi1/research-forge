<script setup lang="ts">
import type { SchemeRiskAssessment } from '@/types'

defineProps<{ risk: SchemeRiskAssessment }>()
</script>

<template>
  <section class="risk-panel">
    <header>
      <p class="section-kicker">Risk Gate</p>
      <strong>{{ risk.hard_constraint_violations.length ? '硬约束未通过' : '硬约束通过' }}</strong>
    </header>
    <div v-if="risk.hard_constraint_violations.length" class="risk-block risk-block--hard">
      <span>阻断接受</span>
      <ul>
        <li v-for="item in risk.hard_constraint_violations" :key="item">{{ item }}</li>
      </ul>
    </div>
    <div v-if="risk.compatibility_risks.length" class="risk-block">
      <span>兼容性风险</span>
      <ul>
        <li v-for="item in risk.compatibility_risks" :key="item">{{ item }}</li>
      </ul>
    </div>
    <div v-if="risk.remaining_risks.length" class="risk-block">
      <span>剩余风险与问题</span>
      <ul>
        <li v-for="item in risk.remaining_risks" :key="item">{{ item }}</li>
      </ul>
    </div>
    <footer>
      <span>{{ risk.diversity_passed ? '差异性通过' : '差异性待核对' }}</span>
      <span>{{ risk.goal_alignment_passed ? '目标对齐' : '目标待调整' }}</span>
      <span>{{ risk.compatibility_passed ? '组合兼容' : '组合待验证' }}</span>
    </footer>
  </section>
</template>
