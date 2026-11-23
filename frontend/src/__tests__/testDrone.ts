import { useFleetStore } from '@/stores/fleet'
import type { DeviceView } from '@/api/drones'

/** RC serial number of the drone the single-drone specs work on (D-31). */
export const TEST_DRONE = 'RC-T'
/** Per-drone endpoint prefix of the test drone. */
export const DP = `/api/v1/drones/${TEST_DRONE}`

export function device(over: Partial<DeviceView> = {}): DeviceView {
  return { droneSn: 'M4E-T', gatewaySn: TEST_DRONE, label: 'A', color: '#378ADD', online: true, droneOnline: true, enabled: true,
    model: 'Matrice 4E', firstSeenAt: 1, lastSeenAt: 1, simulated: true, ...over }
}

/** Registers the test drone(s) in the fleet (without starting stores) and selects the first. */
export function useTestDrone(...extra: DeviceView[]): void {
  const fleet = useFleetStore()
  fleet.drones = [device(), ...extra]
  fleet.selectedSn = TEST_DRONE
}

/** Maps the test drone's endpoint back to the former single-drone path, so specs keep naming the same API. */
export function legacyPath(path: string): string {
  if (!path.startsWith(DP)) return path
  const rest = path.slice(DP.length)
  const renamed: Record<string, string> = { '/state': '/drone/state', '/track': '/drone/track', '/height-limit': '/drone/height-limit' }
  return '/api/v1' + (renamed[rest] ?? rest)
}
