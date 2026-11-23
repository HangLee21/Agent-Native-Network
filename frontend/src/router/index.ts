import { createRouter, createWebHashHistory } from 'vue-router'
import { t } from '@/i18n'

// Hash history keeps static deployment simple (no server rewrite rules needed, C-08).
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/plan' },
    { path: '/plan', name: 'plan', component: () => import('@/views/PlanView.vue'), meta: { title: t('规划') } },
    { path: '/monitor', name: 'monitor', component: () => import('@/views/MonitorView.vue'), meta: { title: t('实时监控') } },
    { path: '/network', name: 'network', component: () => import('@/views/NetworkView.vue'), meta: { title: t('网络观测'), fleet: false } },
    // manual for drones and robot dogs (docs/dog/ui-design.md 5.10); not tied to the selected drone
    { path: '/manual', name: 'manual', component: () => import('@/views/dog/ManualView.vue'), meta: { title: t('使用说明'), fleet: false } },
    // the new dog system while it is tested next to the old one (docs/dog/v2/design.md 4); not tied to a drone
    { path: '/dog2', name: 'dog2', component: () => import('@/views/dogv2/DogV2View.vue'), meta: { title: t('新狗系统'), fleet: false } },
    // the route library lives in the planning page's left panel since 2026-11-04; old links still work
    { path: '/library', redirect: '/plan' },
    { path: '/history', name: 'history', component: () => import('@/views/HistoryView.vue'), meta: { title: t('记录') } },
    // drones' flights and dogs' records together on one map and timeline (D-33, D-40); also one dog record; not tied to the selected drone
    { path: '/history/together', name: 'replay-together', component: () => import('@/views/JointReplayView.vue'), meta: { title: t('一起回放'), fleet: false } },
    { path: '/history/:id', name: 'replay', component: () => import('@/views/ReplayView.vue'), meta: { title: t('飞行回放') } },
    // audience page: follows every drone live and replays records; not tied to the selected drone
    { path: '/watch', name: 'watch', component: () => import('@/views/WatchView.vue'), meta: { title: t('监视台'), fleet: false } },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue'), meta: { title: t('设置') } },
    { path: '/demo/console', name: 'demo-console', component: () => import('@/views/demo/DemoConsoleView.vue'), meta: { title: t('演示控制') } },
    { path: '/demo/show', name: 'demo-show', component: () => import('@/views/demo/DemoShowView.vue'), meta: { title: t('协同演示') } },
  ],
})

export default router
