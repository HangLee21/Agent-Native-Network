import { useControlStore } from './control'
import { useDeviceMessagesStore } from './deviceMessages'
import { useExecutionStore } from './execution'
import { useHistoryStore } from './history'
import { useLiveStore } from './live'
import { useManualStore } from './manual'
import { useOverlaysStore } from './overlays'
import { useTargetsStore } from './targets'
import { useTelemetryStore } from './telemetry'

/** Starts one drone's stores (idempotent): each subscribes to that drone's pushes and loads its state (D-31). */
export function startDroneStores(sn: string): void {
  if (!sn) return
  useTelemetryStore(sn).start()
  useOverlaysStore(sn).start()
  useControlStore(sn).start()
  useExecutionStore(sn).start()
  useLiveStore(sn).start()
  useManualStore(sn).start()
  useDeviceMessagesStore(sn).start()
  useHistoryStore(sn).start()
  useTargetsStore(sn).start()
}
