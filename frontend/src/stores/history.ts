import { perDrone } from './perDrone'
import { ref } from 'vue'
import { historyApi } from '@/api/history'
import { telemetrySocket } from '@/services/ws'
import { useToastStore } from './toast'
import { t } from '@/i18n'

/** Which flight is being recorded right now (D-19); bumps `changed` so open lists refresh. */
export const useHistoryStore = perDrone('history', (sn) => {
  const currentId = ref<string | null>(null)
  const changed = ref(0)
  let started = false

  async function load(): Promise<void> {
    try {
      const st = await historyApi.status()
      currentId.value = st.recorders?.find((r) => r.gatewaySn === sn)?.status.currentSessionId ?? null
    } catch {
      /* backend unreachable */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('history', sn, (m) => {
      const d = m.data as { event: 'started' | 'closed'; id: string }
      if (d.event === 'started') currentId.value = d.id
      if (d.event === 'closed') {
        if (currentId.value === d.id) currentId.value = null
        useToastStore().push('ok', t('飞行记录已保存'), 8000, { label: t('回放'), to: `/history/${d.id}` })
      }
      changed.value++
    })
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  return { sn, currentId, changed, load, start }
})
