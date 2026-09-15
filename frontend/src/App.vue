<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import { useSystemStore } from '@/stores/system'

const route = useRoute()
const system = useSystemStore()
const pageTitle = computed(() => String(route.meta.title ?? 'ResearchForge'))

onMounted(() => void system.refreshHealth())
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <router-link class="brand" to="/status">
        <span class="brand-mark">RF</span>
        <span>
          <strong>ResearchForge</strong>
          <small>科研构思工作台</small>
        </span>
      </router-link>

      <nav class="primary-nav" aria-label="主导航">
        <router-link to="/status"><span>01</span> 系统状态</router-link>
        <router-link to="/projects"><span>02</span> 研究项目</router-link>
        <router-link to="/library"><span>03</span> 全局文献库</router-link>
        <router-link to="/compare"><span>04</span> 文献比较</router-link>
        <router-link to="/search"><span>05</span> 证据检索</router-link>
        <router-link to="/settings"><span>06</span> 系统设置</router-link>
      </nav>

      <div class="sidebar-status">
        <i :class="{ online: system.health?.status === 'healthy' }"></i>
        <div>
          <strong>{{ system.health?.status === 'healthy' ? '系统就绪' : '依赖待检查' }}</strong>
          <small>Milestone 0—6</small>
        </div>
      </div>
    </aside>

    <main>
      <header class="topbar">
        <div>
          <p class="eyebrow">Human × Machine Research</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <router-link class="quick-search" to="/search">⌘ 检索项目证据</router-link>
      </header>
      <div class="page-container">
        <router-view />
      </div>
    </main>
  </div>
</template>
