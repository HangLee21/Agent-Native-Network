import { defineStore } from 'pinia'
import { ref } from 'vue'
import { routesApi, type RouteSummary } from '@/api/routes'
import { ApiError } from '@/api/http'
import { t } from '@/i18n'

export const useRoutesStore = defineStore('routes', () => {
  const list = ref<RouteSummary[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const loaded = ref(false)

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      list.value = await routesApi.list()
      loaded.value = true
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : t('加载失败')
    } finally {
      loading.value = false
    }
  }

  async function remove(id: string): Promise<void> {
    await routesApi.remove(id)
    list.value = list.value.filter((r) => r.id !== id)
  }

  async function duplicate(id: string): Promise<void> {
    await routesApi.duplicate(id)
    await refresh()
  }

  return { list, loading, error, loaded, refresh, remove, duplicate }
})
