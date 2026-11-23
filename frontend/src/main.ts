import './styles/base.css'
import 'leaflet/dist/leaflet.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import { applyDocumentLang, loadLanguage } from './i18n'

async function bootstrap(): Promise<void> {
  applyDocumentLang()
  // English (docs/i18n.md) is loaded before any app module: many of them build label tables with t() when they load
  await loadLanguage()
  const [{ default: App }, { default: router }, { loadRuntimeConfig }] = await Promise.all([
    import('./App.vue'),
    import('./router'),
    import('./config/runtime'),
  ])
  await loadRuntimeConfig()
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
}

void bootstrap()
