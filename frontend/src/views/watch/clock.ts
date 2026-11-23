/** Time formatting for the 监视台 (no map dependencies, so the engine and tests can use it). */
import { dateLocale } from '@/i18n'
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const fmtHMS = new Intl.DateTimeFormat(dateLocale(), { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
const fmtHM = new Intl.DateTimeFormat(dateLocale(), { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** Added to every time shown on the page: 「假装实时」 shows a recorded flight at today's clock time. */
let displayOffset = 0
export function setDisplayOffset(ms: number): void { displayOffset = ms }
export const clockStr = (t: number, tenths = false) => {
  if (!isNum(t)) return '--:--:--'
  const v = t + displayOffset
  const s = fmtHMS.format(new Date(v))
  return tenths ? s + '.' + Math.floor((((v % 1000) + 1000) % 1000) / 100) : s
}
export const hmStr = (t: number) => (isNum(t) ? fmtHM.format(new Date(t + displayOffset)) : '--:--')
export function durStr(ms: number, signed = false): string {
  if (!isNum(ms)) return '–'
  const neg = ms < 0
  let s = Math.floor(Math.abs(ms) / 1000)
  const h = Math.floor(s / 3600); s -= h * 3600
  const m = Math.floor(s / 60); s -= m * 60
  const body = (h ? h + ':' + String(m).padStart(2, '0') : String(m).padStart(2, '0')) + ':' + String(s).padStart(2, '0')
  return signed ? (neg ? 'T−' : 'T+') + body : (neg ? '−' : '') + body
}
