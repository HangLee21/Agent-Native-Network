import { reactive } from 'vue'
import { watchApi, type WatchSettings } from '@/api/watch'
import { telemetrySocket } from '@/services/ws'
import { t } from '@/i18n'

/** State of the 演示与监视台 settings section. Every change saves at once (shared by every monitor screen). */
export function useWatchSettings() {
  const s = reactive({
    value: null as WatchSettings | null,
    saving: false,
    error: null as string | null,
    async load(): Promise<void> {
      try { s.value = await watchApi.settings(); s.error = null } catch (e) { s.error = e instanceof Error ? e.message : t('读取失败') }
    },
    async save(patch: Partial<WatchSettings>): Promise<void> {
      const before = s.value
      if (s.value) s.value = { ...s.value, ...patch }
      s.saving = true
      try { s.value = await watchApi.updateSettings(patch); s.error = null } catch (e) { s.value = before; s.error = e instanceof Error ? e.message : t('保存失败') } finally { s.saving = false }
    },
  })
  telemetrySocket.on('monitor-settings', (m) => { s.value = m.data as WatchSettings })
  void s.load()
  return s
}
export type WatchSettingsState = ReturnType<typeof useWatchSettings>
