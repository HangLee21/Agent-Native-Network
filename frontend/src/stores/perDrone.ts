import { defineStore } from 'pinia'
import { useDroneSn } from '@/composables/useDrone'

/**
 * A store with one instance per drone (D-31): `use(sn)` gives that drone's instance, `use()` the instance of the
 * drone the calling code works on (its drone scope, else the selected drone). The setup body is the former
 * single-drone store, now bound to `sn`.
 */
export function perDrone<SS extends object>(name: string, setup: (sn: string) => SS) {
  const make = (sn: string) => defineStore(`${name}:${sn}`, () => setup(sn))
  const defs = new Map<string, ReturnType<typeof make>>()
  return (sn?: string): ReturnType<ReturnType<typeof make>> => {
    const key = sn ?? useDroneSn()
    let def = defs.get(key)
    if (!def) {
      def = make(key)
      defs.set(key, def)
    }
    return def()
  }
}
