import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/status' },
    { path: '/status', component: () => import('@/views/StatusView.vue'), meta: { title: '系统状态' } },
    { path: '/projects', component: () => import('@/views/ProjectsView.vue'), meta: { title: '研究项目' } },
    {
      path: '/projects/:id',
      component: () => import('@/views/ProjectView.vue'),
      meta: { title: '项目工作台' },
    },
    { path: '/library', component: () => import('@/views/LibraryView.vue'), meta: { title: '全局文献库' } },
    {
      path: '/papers/:id',
      component: () => import('@/views/PaperView.vue'),
      meta: { title: '论文知识卡' },
    },
    { path: '/compare', component: () => import('@/views/CompareView.vue'), meta: { title: '文献比较' } },
    { path: '/search', component: () => import('@/views/SearchView.vue'), meta: { title: '证据检索' } },
    {
      path: '/settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: '系统设置' },
    },
    {
      path: '/projects/:id/ideas',
      component: () => import('@/views/IdeasView.vue'),
      meta: { title: '个人想法' },
    },
    {
      path: '/projects/:id/schemes',
      component: () => import('@/views/SchemesView.vue'),
      meta: { title: '研究构思工作台' },
    },
    {
      path: '/schemes/:id',
      component: () => import('@/views/SchemeView.vue'),
      meta: { title: '候选方案详情' },
    },
  ],
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title)} · ResearchForge`
})

export default router
