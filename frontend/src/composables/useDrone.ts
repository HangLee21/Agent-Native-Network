import { getCurrentInstance, inject, provide, type InjectionKey } from 'vue'
import { useFleetStore } from '@/stores/fleet'

/** RC serial number of the drone a component subtree works on (D-31). */
export const DRONE_KEY: InjectionKey<string> = Symbol('drone')

/**
 * Binds a component subtree to one drone: stores and API calls made from inside go to that drone, even if the
 * operator selects another one while, say, a confirmation dialog is open (D-31).
 */
export function provideDrone(sn: string): void {
  provide(DRONE_KEY, sn)
}

/**
 * The drone this code works on: the enclosing drone scope's, else the selected drone ('' while none is known).
 * Called during component setup, the result is fixed for the component's lifetime.
 */
export function useDroneSn(): string {
  if (getCurrentInstance()) {
    const scoped = inject(DRONE_KEY, null)
    if (scoped) return scoped
  }
  return useFleetStore().selectedSn ?? ''
}
