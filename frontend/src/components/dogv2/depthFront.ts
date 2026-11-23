import type { Dog2 } from '@/api/dogv2'
import { t } from '@/i18n'

/**
 * The line under the Lite3 depth video: the front depth distance the old Lite3 card showed ("中心深度 X m（有效 Y%）",
 * the 2 % quantile of the valid depths in the centre of the depth image, telemetry.depth_front, protocol.md section 7).
 * A depth image older than 0.5 s gives no number (the old console's limit, 建图导航-现状.md section 2).
 * null: the dog does not report it (a board without the depth reader), so nothing is shown.
 */
export const DEPTH_FRONT_STALE_S = 0.5

export function depthFrontText(d: Dog2 | null | undefined): string | null {
  const f = d?.telemetry?.depth_front
  if (!d || !f) return null
  if (!d.online || d.mode !== 'new' || (d.telemetryAgeMs ?? Infinity) >= 3000) return t('中心深度 —')
  if (f.state === 'error') return t('中心深度 —（读取深度图出错）')
  if (f.age_s == null) return f.valid_pct == null ? t('中心深度 —（没有深度图）') : t('中心深度 —（深度图时间不对）')
  if (f.age_s > DEPTH_FRONT_STALE_S) {
    return t('中心深度 —（深度图 {n} 秒没更新）', { n: f.age_s < 10 ? f.age_s.toFixed(1) : Math.round(f.age_s) })
  }
  const pct = Math.round(f.valid_pct ?? 0)
  if (f.dist_m == null) return t('中心深度 —（有效 {pct}%）', { pct })
  return t('中心深度 {m} m（有效 {pct}%）', { m: f.dist_m.toFixed(2), pct })
}

/**
 * The same number for a chip: "1.80 m" when there is one, else "—" with the full line as the hover text (ui-design.md
 * 20.3). `cls` is grey when the dog does not report it, amber when it reports it but there is no number now.
 */
export function depthFrontShort(d: Dog2 | null | undefined): { text: string; cls: '' | 'warnc' | 'dim'; title: string } {
  const line = depthFrontText(d)
  if (line == null) return { text: '—', cls: 'dim', title: t('这只狗不报中心深度') }
  const f = d!.telemetry!.depth_front!
  const fresh = d!.online && d!.mode === 'new' && (d!.telemetryAgeMs ?? Infinity) < 3000 && f.state !== 'error'
    && f.age_s != null && f.age_s <= DEPTH_FRONT_STALE_S && f.dist_m != null
  return fresh ? { text: `${f.dist_m!.toFixed(2)} m`, cls: '', title: line } : { text: '—', cls: 'warnc', title: line }
}
