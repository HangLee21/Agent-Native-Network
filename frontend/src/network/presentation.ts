import { t } from '@/i18n'
import { linkEvidenceState } from './model'
import type { NetworkEvent, NetworkLink, NetworkSnapshot, NodeRole, NodeTag, ObservationState } from './types'

export function linkEvidenceLabel(e: NetworkLink, snapshot: NetworkSnapshot, now: number, interrupted = false): string {
  switch (linkEvidenceState(e, snapshot, now, interrupted)) {
    case 'recent-sample': return t('近期邻居采样 · 有效期未知')
    case 'older-sample': return t('较早邻居采样 · 有效期未知')
    case 'report-stale': return t('报告超时 · 仅保留采样')
    case 'expired': return t('采样已过期')
    case 'unknown': return t('有效性未知')
    case 'interrupted': return t('观测中断 · 保留采样')
    case 'lost': return t('节点上报失效')
    case 'current': return e.kind === 'lora' ? t('近期上行接收') : e.state === 'mutual' ? t('新鲜双向互证') : t('单向收到 · 非端到端交付')
  }
}
export const reportedLinkLabel = (e: NetworkLink) => ({ mutual: t('报告中双向'), oneway: t('报告中单向'), lost: t('报告中失效'), unknown: t('报告未说明') })[e.state]

export const roleLabel = (role: NodeRole) => role === 'gateway' ? t('接收网关') : 'NODE'
export const tagLabel = (tag: NodeTag) => tag === 'drone' ? t('标签：无人机') : tag === 'robot' ? t('标签：机器人') : 'NODE'
export const stateLabel = (state: ObservationState) => ({ recent: t('近期报告'), stale: t('报告超时'), unknown: t('从未观测'), interrupted: t('观测中断') })[state]
export const eventLabel = (code: NetworkEvent['code']) => ({ report_received: t('收到节点报告'), link_changed: t('链路采样变化'), receiver_recovered: t('接收器恢复'), receiver_interrupted: t('接收器观测中断') })[code]
export function ageText(value: number | null | undefined): string { return value == null || !Number.isFinite(value) ? '—' : value < 1000 ? `${Math.max(0, Math.round(value))} ms` : `${(Math.max(0, value) / 1000).toFixed(1)} s` }
export function timeText(at: number | null | undefined): string { return at == null ? '—' : new Date(at).toLocaleTimeString('en-GB', { hour12: false }) }
