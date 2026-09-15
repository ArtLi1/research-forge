<script setup lang="ts">
import type { KnowledgeCard } from '@/types'

defineProps<{ card: KnowledgeCard }>()
</script>

<template>
  <div class="knowledge-card">
    <header class="knowledge-card__summary">
      <div>
        <p class="section-kicker">Inspiration Knowledge · V{{ card.version_number }}</p>
        <h2>论文启发知识卡</h2>
      </div>
      <div class="knowledge-status">
        <span>结构校验通过</span>
        <small>{{ card.extraction_model }}</small>
      </div>
      <p>聚焦可迁移的研究场景与算法机制，不保存原文证据链。</p>
    </header>

    <div class="knowledge-sections">
      <section v-if="card.content.scenarios.length" class="knowledge-field">
        <div class="knowledge-field__title">
          <span>研究场景</span>
          <small>{{ card.content.scenarios.length }}</small>
        </div>
        <article v-for="item in card.content.scenarios" :key="item.name">
          <h3>{{ item.name }}</h3>
          <p>{{ item.description }}</p>
          <footer><span>关键挑战：{{ item.key_challenge }}</span></footer>
          <p v-if="item.innovation_point">创新点：{{ item.innovation_point }}</p>
        </article>
      </section>

      <section v-if="card.content.algorithms.length" class="knowledge-field">
        <div class="knowledge-field__title">
          <span>算法知识</span>
          <small>{{ card.content.algorithms.length }}</small>
        </div>
        <article v-for="item in card.content.algorithms" :key="item.name">
          <h3>{{ item.name }}</h3>
          <p>{{ item.core_idea }}</p>
          <footer><span>关键机制：{{ item.key_mechanism }}</span></footer>
          <p>创新点：{{ item.innovation_point }}</p>
        </article>
      </section>
    </div>
  </div>
</template>
