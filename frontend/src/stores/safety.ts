import { defineStore } from 'pinia'
import { ref } from 'vue'
import { safetyApi, type SafetyConfig } from '@/api/safety'
import { telemetrySocket } from '@/services/ws'
import { useMapOverlaysStore } from './overlays'

/** Safety configuration (S-01, S-02); keeps the safe-zone map layer in sync. */
export const useSafetyStore = defineStore('safety', () => {
  const config = ref<SafetyConfig | null>(null)
  let started = false

  function apply(c: SafetyConfig): void {
    config.value = c
    const ov = useMapOverlaysStore()
    ov.safeZone = c.safeZoneEnabled && c.safeZone.length >= 3 ? c.safeZone.map(([lat, lon]) => ({ lat, lon })) : null
  }

  async function load(): Promise<void> {
    try {
      apply(await safetyApi.config())
    } catch {
      /* backend unreachable */
    }
  }

  async function update(c: Partial<SafetyConfig>): Promise<void> {
    apply(await safetyApi.update(c))
  }

  function start(): void {
    if (started) return
    started = true
    telemetrySocket.on('safety-config', (m) => apply(m.data as SafetyConfig))
    void load()
  }

  return { config, apply, load, update, start }
})
