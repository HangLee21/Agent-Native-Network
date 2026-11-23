import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { safetyApi, type SafetyCheckResult } from '@/api/safety'
import { ApiError } from '@/api/http'
import { useEditorStore } from '@/stores/editor'
import { useSafetyStore } from '@/stores/safety'
import { t } from '@/i18n'

/** Debounced live safety check of the route being edited (ui-design.md §4.1 step 4). */
export function useRouteSafety(delayMs = 500) {
  const ed = useEditorStore()
  const safety = useSafetyStore()
  const result = ref<SafetyCheckResult | null>(null)
  const checking = ref(false)
  const error = ref<string | null>(null)
  let timer: number | undefined
  let seq = 0

  async function run(): Promise<void> {
    if (!ed.draft || ed.draft.waypoints.length === 0) {
      result.value = null
      return
    }
    const mine = ++seq
    checking.value = true
    try {
      const req = ed.request()
      const r = await safetyApi.checkRoute({ ...req, name: req.name || t('未命名') })
      if (mine === seq) {
        result.value = r
        error.value = null
      }
    } catch (e) {
      if (mine === seq) error.value = e instanceof ApiError ? e.message : t('请求失败')
    } finally {
      if (mine === seq) checking.value = false
    }
  }

  watch(
    () => [ed.draft, safety.config],
    () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => void run(), delayMs)
    },
    { deep: true, immediate: true },
  )
  onBeforeUnmount(() => window.clearTimeout(timer))

  const invalid = computed(() => new Set((result.value?.violations ?? []).map((v) => v.waypointIndex).filter((i): i is number => i !== null)))
  return { result, checking, error, invalid, run }
}
