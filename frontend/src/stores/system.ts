import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/http'

export interface GatewayInfo {
  mode: string
  gatewaySn: string
  droneSn: string
  gatewayOnline: boolean
  droneOnline: boolean
  droneModel: string | null
  rcModel: string | null
}

export interface SystemInfo {
  name: string
  version: string
  gatewayMode: string
  /** The only enabled drone (single-drone clients); null with several — see `drones` (D-29). */
  gateway: GatewayInfo | null
  routeExecutionMode: string
  serverTime: number
}

export type Theme = 'dark' | 'outdoor'

const THEME_KEY = 'uav.theme'

function readTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'outdoor' ? 'outdoor' : 'dark'
  } catch {
    return 'dark'
  }
}

export const useSystemStore = defineStore('system', () => {
  const info = ref<SystemInfo | null>(null)
  const backendReachable = ref<boolean | null>(null)
  const theme = ref<Theme>(readTheme())

  async function refresh(): Promise<void> {
    try {
      info.value = await api<SystemInfo>('/api/v1/system/info')
      backendReachable.value = true
    } catch {
      backendReachable.value = false
    }
  }

  function applyTheme(t: Theme): void {
    theme.value = t
    document.documentElement.dataset.theme = t
    try {
      localStorage.setItem(THEME_KEY, t)
    } catch {
      /* storage unavailable: theme still applies for this session */
    }
  }

  return { info, backendReachable, theme, refresh, applyTheme }
})
