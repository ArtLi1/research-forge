<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getSystemSettings } from '@/api'
import type { SystemSettings } from '@/types'

const settings = ref<SystemSettings | null>(null)

onMounted(async () => {
  settings.value = await getSystemSettings()
})
</script>

<template>
  <section class="settings-ledger reveal">
    <header>
      <p class="section-kicker">Runtime Ledger</p>
      <h2>当前运行配置</h2>
      <p>此页面只展示非敏感配置；API Key 永不返回前端。</p>
    </header>
    <div v-if="settings" class="settings-grid">
      <article>
        <small>Chat Model</small>
        <strong>{{ settings.llm_model || '未配置' }}</strong>
        <span>{{ settings.llm_base_url || '—' }}</span>
        <em>{{ settings.llm_api_key_configured ? '密钥已配置' : '密钥未配置' }}</em>
      </article>
      <article>
        <small>Embedding</small>
        <strong>{{ settings.embedding_model }}</strong>
        <span>{{ settings.embedding_provider }}</span>
        <em>Chroma 默认模型</em>
      </article>
      <article>
        <small>Vector Store</small>
        <strong>{{ settings.chroma_endpoint }}</strong>
        <span>{{ settings.chroma_data_dir }}</span>
        <em>本机持久化服务</em>
      </article>
    </div>
    <aside v-if="settings">
      <strong>第三方模型提示</strong>
      <p>{{ settings.third_party_notice }}</p>
    </aside>
  </section>
</template>
