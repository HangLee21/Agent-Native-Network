import { perDrone } from './perDrone'
import { ref } from 'vue'
import { liveApi, type LiveStatus } from '@/api/live'
import { telemetrySocket } from '@/services/ws'

export const useLiveStore = perDrone('live', (sn) => {
  const status = ref<LiveStatus | null>(null)
  let started = false

  async function load(): Promise<void> {
    try {
      status.value = await liveApi(sn).status()
    } catch {
      /* backend unreachable */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('live', sn, () => void load())
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  return { sn, status, load, start }
})
