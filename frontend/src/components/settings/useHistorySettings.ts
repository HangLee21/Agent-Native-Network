/**
 * Flight recording status and the video recording switch (D-19, D-20). Loaded when the settings page opens,
 * as HistorySettingsCard did before the page was split into sections, so the navigation can show the
 * recording state. The switch saves immediately and reloads the status.
 */
import { onMounted, reactive, ref } from 'vue'
import { ApiError } from '@/api/http'
import { historyApi, type HistoryStatus } from '@/api/history'
import { useToastStore } from '@/stores/toast'
import { t } from '@/i18n'

export function useHistorySettings() {
  const toast = useToastStore()
  const status = ref<HistoryStatus | null>(null)
  const error = ref<string | null>(null)
  const saving = ref(false)

  async function load(): Promise<void> {
    try {
      status.value = await historyApi.status()
      error.value = null
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : t('加载失败')
    }
  }

  async function setVideo(on: boolean): Promise<void> {
    saving.value = true
    try {
      await historyApi.updateSettings(on)
      toast.push('ok', on ? t('已开启录像（从下一次起飞起生效）') : t('已关闭录像（从下一次起飞起生效）'))
      await load()
    } catch (e) {
      toast.push('danger', e instanceof ApiError ? e.message : t('保存失败'))
    } finally {
      saving.value = false
    }
  }

  onMounted(load)

  return reactive({ status, error, saving, load, setVideo })
}

export type HistorySettings = ReturnType<typeof useHistorySettings>
