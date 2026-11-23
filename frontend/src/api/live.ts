import { ApiError, api } from './http'
import { dronePath } from './drone'
import { t } from '@/i18n'
import type { CommandRecord } from './control'

export interface Playback {
  protocol: 'WHEP' | 'HLS' | 'MOCK' | 'NONE'
  url: string | null
  fallbackUrl?: string | null
}

export interface LiveStatus {
  videoId: string | null
  streaming: boolean
  quality: number
  lens: string
  playback: Playback | null
  lenses: string[]
  pushConfigured: boolean
}

export const QUALITY_LABELS: Record<number, string> = { 0: t('自适应'), 1: t('流畅 540p'), 2: t('标清 720p'), 3: t('高清 720p'), 4: t('超清 1080p') }
export const LENS_LABELS: Record<string, string> = { wide: t('广角'), zoom: t('变焦'), thermal: t('红外'), ir: t('红外') }

/** Per-drone endpoints (D-29): sn is the RC serial number. */
export const liveApi = (sn: string) => ({
  status: () => api<LiveStatus>(dronePath(sn, '/live')),
  start: (quality: number) => api<CommandRecord>(dronePath(sn, '/live/start'), { method: 'POST', body: { quality } }),
  stop: () => api<CommandRecord>(dronePath(sn, '/live/stop'), { method: 'POST' }),
  quality: (quality: number) => api<CommandRecord>(dronePath(sn, '/live/quality'), { method: 'POST', body: { quality } }),
  lens: (lens: string) => api<CommandRecord>(dronePath(sn, '/live/lens'), { method: 'POST', body: { lens } }),
})

/** Minimal WHEP (WebRTC-HTTP egress) client for self-hosted media servers such as MediaMTX. */
export async function playWhep(url: string, video: HTMLVideoElement, signal?: AbortSignal): Promise<RTCPeerConnection> {
  signal?.throwIfAborted()
  const pc = new RTCPeerConnection()
  try {
    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })
    pc.ontrack = (ev) => {
      if (!signal?.aborted && ev.streams[0]) video.srcObject = ev.streams[0]
    }
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const res = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/sdp' }, body: offer.sdp ?? '', signal,
    })
    if (!res.ok) {
      throw new ApiError(t('WHEP 请求失败（HTTP {status}）', { status: res.status }), res.status)
    }
    const sdp = await res.text()
    signal?.throwIfAborted()
    await pc.setRemoteDescription({ type: 'answer', sdp })
    signal?.throwIfAborted()
    return pc
  } catch (error) {
    pc.close()
    throw error
  }
}
