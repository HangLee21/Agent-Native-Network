import { perDrone } from './perDrone'
import { computed, ref } from 'vue'
import { deviceMessagesApi, type DeviceMessage, type Obstacles } from '@/api/deviceMessages'
import { telemetrySocket } from '@/services/ws'
import { useToastStore } from './toast'

/** Device messages and obstacle distances pushed by the platform (D-18). */
export const useDeviceMessagesStore = perDrone('deviceMessages', (sn) => {
  const list = ref<DeviceMessage[]>([])
  const obstacles = ref<Obstacles | null>(null)
  const unread = ref(0)
  let started = false

  const warnings = computed(() => list.value.filter((m) => m.level !== 'INFO').length)

  function add(m: DeviceMessage, notify = true): void {
    if (list.value.some((x) => x.id === m.id)) return
    list.value.unshift(m)
    if (list.value.length > 100) list.value.length = 100
    unread.value++
    if (notify && m.level !== 'INFO') useToastStore().push(m.level === 'CRITICAL' ? 'danger' : 'warn', `${m.title}：${m.text}`, 6000)
  }

  async function load(): Promise<void> {
    try {
      const r = await deviceMessagesApi(sn).list()
      list.value = r.list
      obstacles.value = r.obstacles
    } catch {
      /* backend unreachable */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('deviceMessage', sn, (m) => add(m.data as DeviceMessage))
    telemetrySocket.onDrone('obstacle', sn, (m) => (obstacles.value = m.data as Obstacles))
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  return { sn, list, obstacles, unread, warnings, add, load, start }
})
