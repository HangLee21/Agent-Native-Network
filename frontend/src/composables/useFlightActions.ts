import { computed, ref, type Ref } from 'vue'
import { controlApi, type TakeoffRequest } from '@/api/control'
import { useDroneSn } from '@/composables/useDrone'
import { useFleetStore } from '@/stores/fleet'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useConfirmStore } from '@/stores/confirm'
import { t } from '@/i18n'

/** Per drone; shared by the side panel footer and the collapsed rail; the monitor view renders the dialog. */
const takeoffOpen = new Map<string, Ref<boolean>>()

function openRef(sn: string): Ref<boolean> {
  let r = takeoffOpen.get(sn)
  if (!r) {
    r = ref(false)
    takeoffOpen.set(sn, r)
  }
  return r
}

/**
 * Take-off / return home / cancel return (R-10, R-11), unchanged calls and confirmations. They share one
 * place (ui-design.md §5): 一键起飞 only while the aircraft is online and on the ground; in every other
 * case (including lost telemetry) 一键返航, or 取消返航 while returning (mode_code 9).
 */
export function useFlightActions(droneSn?: string) {
  const sn = droneSn ?? useDroneSn()
  const control = useControlStore(sn)
  const tel = useTelemetryStore(sn)
  const confirm = useConfirmStore()
  const name = () => useFleetStore().label(sn)
  const open = openRef(sn)

  const slot = computed<'takeoff' | 'rth' | 'cancel'>(() => {
    if (tel.online && !tel.airborne) return 'takeoff'
    return tel.drone?.modeCode === 9 ? 'cancel' : 'rth'
  })

  async function takeoff(r: TakeoffRequest): Promise<void> {
    open.value = false
    await control.run('takeoff', t('一键起飞'), () => controlApi(sn).takeoff(r))
  }

  async function returnHome(): Promise<void> {
    if (!(await confirm.ask({ title: t('确认让 {name} 返航', { name: name() }), message: t('飞行器将按返航高度飞回 Home 点并降落。'), confirmText: t('返航'), focus: 'confirm' }))) return
    await control.run('rth', t('一键返航'), () => controlApi(sn).returnHome())
  }

  const cancelReturn = () => control.run('rth', t('取消返航'), () => controlApi(sn).cancelReturnHome())

  return { slot, takeoffOpen: open, takeoff, returnHome, cancelReturn }
}
