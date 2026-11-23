import { ApiError } from './http'
import { t } from '@/i18n'

/** Path of a per-drone endpoint (D-29): /api/v1/drones/{sn}/…; sn is the RC serial number. */
export function dronePath(sn: string, path: string): string {
  if (!sn) throw new ApiError(t('未选择飞机'), 0)
  return `/api/v1/drones/${encodeURIComponent(sn)}${path}`
}
