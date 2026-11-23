import { dateLocale, t } from '@/i18n'

/** Display helpers. Labels follow the M4 property enumerations (research-notes Q-04). */
export const MODE_CODE_LABELS: Record<number, string> = {
  0: t('待机'),
  1: t('起飞准备'),
  2: t('起飞准备完毕'),
  3: t('手动飞行'),
  4: t('自动起飞'),
  5: t('航线飞行'),
  6: t('全景拍照'),
  7: t('智能跟随'),
  8: t('ADS-B 躲避'),
  9: t('自动返航'),
  10: t('自动降落'),
  11: t('强制降落'),
  12: t('三桨叶降落'),
  13: t('升级中'),
  14: t('未连接'),
  15: 'APAS',
  16: t('虚拟摇杆'),
  17: t('指令飞行'),
  18: t('空中 RTK 收敛'),
  19: t('机场选址中'),
}

export const WIND_DIRECTIONS: Record<number, string> = {
  1: t('北'), 2: t('东北'), 3: t('东'), 4: t('东南'), 5: t('南'), 6: t('西南'), 7: t('西'), 8: t('西北'),
}

export const GEAR_LABELS: Record<number, string> = {
  0: 'A', 1: 'P', 2: 'NAV', 3: 'FPV', 4: 'FARM', 5: 'S', 6: 'F', 7: 'M', 8: 'G', 9: 'T',
}

export function modeLabel(code: number | null | undefined): string {
  if (code === null || code === undefined) return '—'
  return MODE_CODE_LABELS[code] ?? t('状态 {code}', { code })
}

export function num(v: number | null | undefined, digits = 1, unit = ''): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toFixed(digits) + (unit ? ` ${unit}` : '')
}

export function coord(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : v.toFixed(7)
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export function meters(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v >= 1000 ? `${(v / 1000).toFixed(2)} km` : `${Math.round(v)} m`
}

/** File size: 850 KB, 12.3 MB, 1.2 GB. */
export function bytes(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)} GB`
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)} MB`
  return `${Math.max(1, Math.round(v / 1e3))} KB`
}

export function time(ts: number | null | undefined): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleTimeString(dateLocale(), { hour12: false })
}

export function dateTime(ts: number | null | undefined): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString(dateLocale(), { hour12: false })
}
