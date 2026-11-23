/**
 * Reconnecting WebSocket client for /ws/telemetry. Messages: {type, ts, data}; messages about one drone also carry
 * droneSn and gatewaySn (D-29), platform-level ones do not.
 */
import { config } from '@/config/runtime'
import { translateIncoming } from '@/i18n'

export interface WsMessage<T = unknown> {
  type: string
  ts: number
  data: T
  droneSn?: string | null
  gatewaySn?: string | null
}

type Handler = (msg: WsMessage) => void

class TelemetrySocket {
  private socket: WebSocket | null = null
  private handlers = new Map<string, Set<Handler>>()
  private statusHandlers = new Set<(connected: boolean) => void>()
  private retry = 0
  private timer: number | undefined
  private stopped = false

  start(): void {
    this.stopped = false
    if (this.socket) return
    this.open()
  }

  stop(): void {
    this.stopped = true
    window.clearTimeout(this.timer)
    this.socket?.close()
    this.socket = null
  }

  on(type: string, handler: Handler): () => void {
    const set = this.handlers.get(type) ?? new Set<Handler>()
    set.add(handler)
    this.handlers.set(type, set)
    return () => set.delete(handler)
  }

  /** Messages of this type about one drone (by RC serial number). */
  onDrone(type: string, gatewaySn: string, handler: Handler): () => void {
    return this.on(type, (m) => {
      if (m.gatewaySn === gatewaySn) handler(m)
    })
  }

  onStatus(handler: (connected: boolean) => void): () => void {
    this.statusHandlers.add(handler)
    return () => this.statusHandlers.delete(handler)
  }

  /** Dispatches a message as if it came from the server (used by tests). */
  dispatch(msg: WsMessage): void {
    this.handlers.get(msg.type)?.forEach((h) => h(msg))
    this.handlers.get('*')?.forEach((h) => h(msg))
  }

  private open(): void {
    let ws: WebSocket
    try {
      ws = new WebSocket(config().wsUrl)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.socket = ws
    ws.onopen = () => {
      this.retry = 0
      this.statusHandlers.forEach((h) => h(true))
    }
    ws.onmessage = (ev: MessageEvent<string>) => {
      try {
        this.dispatch(translateIncoming(JSON.parse(ev.data) as WsMessage))
      } catch {
        /* ignore malformed frame */
      }
    }
    ws.onclose = () => {
      this.socket = null
      this.statusHandlers.forEach((h) => h(false))
      this.scheduleReconnect()
    }
    ws.onerror = () => ws.close()
  }

  private scheduleReconnect(): void {
    if (this.stopped) return
    const delay = Math.min(10000, 500 * 2 ** this.retry)
    this.retry++
    this.timer = window.setTimeout(() => this.open(), delay)
  }
}

export const telemetrySocket = new TelemetrySocket()
