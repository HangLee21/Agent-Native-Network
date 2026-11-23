import { perDrone } from './perDrone'
import { ref } from 'vue'
import { manualApi, type ManualSnapshot } from '@/api/manual'
import { ApiError } from '@/api/http'
import { telemetrySocket } from '@/services/ws'
import { t } from '@/i18n'

/** Stick control mode (R-13, D-16): state comes from the backend, which owns the stream to the aircraft. */
export const useManualStore = perDrone('manual', (sn) => {
  const snapshot = ref<ManualSnapshot | null>(null)
  const error = ref<string | null>(null)
  let started = false

  async function call(fn: () => Promise<ManualSnapshot>): Promise<boolean> {
    try {
      snapshot.value = await fn()
      error.value = null
      return true
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : t('请求失败')
      return false
    }
  }

  const enter = (scale: number) => call(() => manualApi(sn).enter(scale))
  const exit = () => call(() => manualApi(sn).exit())
  const setScale = (scale: number) => call(() => manualApi(sn).scale(scale))

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('manual', sn, (m) => (snapshot.value = m.data as ManualSnapshot))
    telemetrySocket.onStatus((c) => c && void call(() => manualApi(sn).state()))
    void call(() => manualApi(sn).state())
  }

  return { sn, snapshot, error, enter, exit, setScale, start }
})
