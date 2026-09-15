<script setup lang="ts">
import { onMounted } from 'vue'

import { useSystemStore } from '@/stores/system'

const system = useSystemStore()
onMounted(() => void system.refreshHealth())

const serviceNames: Record<string, string> = {
  application: 'FastAPI',
  postgres: 'PostgreSQL',
  redis: 'Redis / RQ',
  chroma: 'Chroma',
}
</script>

<template>
  <section class="hero-card reveal">
    <div>
      <p class="section-kicker">系统脉搏</p>
      <h2>知识流水线，<br />从论文原页开始。</h2>
      <p>
        当前工程已覆盖项目管理、全局文献复用、异步 PDF 解析、领域分块与项目级语义检索。
      </p>
    </div>
    <div class="health-orbit" :class="{ healthy: system.health?.status === 'healthy' }">
      <span>{{ system.health?.status === 'healthy' ? 'READY' : 'CHECK' }}</span>
      <small>依赖健康状态</small>
    </div>
  </section>

  <section class="service-grid reveal delay-1">
    <article v-for="(service, key) in system.health?.services" :key="key" class="service-card">
      <div class="service-card__head">
        <span>{{ serviceNames[key] ?? key }}</span>
        <i :class="{ online: service.status === 'healthy' }"></i>
      </div>
      <strong>{{ service.status === 'healthy' ? '运行正常' : '连接异常' }}</strong>
      <p>{{ service.detail || '健康检查通过，连接可用。' }}</p>
    </article>
    <article v-if="!system.health" class="service-card service-card--loading">
      正在读取服务状态…
    </article>
  </section>

  <section class="pipeline reveal delay-2">
    <p class="section-kicker">当前处理链路</p>
    <div class="pipeline-steps">
      <span>PDF 上传</span><i>→</i><span>哈希去重</span><i>→</i><span>章节解析</span><i>→</i
      ><span>领域分块</span><i>→</i><span>Chroma 索引</span>
    </div>
  </section>
</template>
