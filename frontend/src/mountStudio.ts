import './styles/base.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { applyDocumentLang, loadLanguage } from './i18n'
import type { Workspace } from './network/types'

export async function mountStudio(workspace: Workspace) {
  applyDocumentLang()
  await loadLanguage()
  const { default: App } = await import('./NetworkStudioApp.vue')
  createApp(App, { workspace }).use(createPinia()).mount('#app')
}
