import { t } from '@/i18n'
import type { NetworkEvent, NodeRole, NodeTag, ObservationState } from './types'
export const roleLabel = (role: NodeRole) => role === 'gateway' ? t('接收网关') : 'NODE'
export const tagLabel = (tag: NodeTag) => tag === 'drone' ? t('标签：无人机') : tag === 'robot' ? t('标签：机器人') : 'NODE'
export const stateLabel = (state: ObservationState) => ({ recent: t('近期报告'), stale: t('报告超时'), unknown: t('从未观测'), interrupted: t('观测中断') })[state]
export const eventLabel = (code: NetworkEvent['code']) => ({ report_received: t('收到节点报告'), link_changed: t('链路采样变化'), receiver_recovered: t('接收器恢复'), receiver_interrupted: t('接收器观测中断') })[code]
export function ageText(value: number | null | undefined): string { return value == null || !Number.isFinite(value) ? '—' : value < 1000 ? `${Math.max(0, Math.round(value))} ms` : `${(Math.max(0, value) / 1000).toFixed(1)} s` }
export function timeText(at: number | null | undefined): string { return at == null ? '—' : new Date(at).toLocaleTimeString('en-GB', { hour12: false }) }
