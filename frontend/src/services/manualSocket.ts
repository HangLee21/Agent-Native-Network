/**
 * Browser → platform input frames for stick control and gimbal hold (/ws/manual?droneSn=…, D-16, D-29).
 * One socket per drone, opened on first use; frames are dropped while it is not open (the server then applies its
 * dead-man).
 */
import { config } from '@/config/runtime'

export function manualUrl(wsUrl: string, sn?: string): string {
  const base = wsUrl.replace(/\/ws\/telemetry\/?$/, '/ws/manual')
  return sn ? `${base}?droneSn=${encodeURIComponent(sn)}` : base
}

class ManualSocket {
  private socket: WebSocket | null = null
  private wanted = false

  constructor(private readonly sn: string) {}

  /** Keeps the socket open while inputs may be sent (stick mode or a held gimbal button). */
  ensure(): void {
    this.wanted = true
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return
    try {
      const ws = new WebSocket(manualUrl(config().wsUrl, this.sn))
      ws.onclose = () => {
        this.socket = null
        if (this.wanted) window.setTimeout(() => this.wanted && this.ensure(), 1000)
      }
      ws.onerror = () => ws.close()
      this.socket = ws
    } catch {
      this.socket = null
    }
  }

  release(): void {
    this.wanted = false
    this.socket?.close()
    this.socket = null
  }

  private send(frame: object): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(frame))
  }

  stick(roll: number, pitch: number, throttle: number, yaw: number): void {
    this.send({ t: 'stick', roll, pitch, throttle, yaw })
  }

  gimbal(pitch: number, yaw: number): void {
    this.send({ t: 'gimbal', pitch, yaw })
  }
}

const sockets = new Map<string, ManualSocket>()

/** The input socket of one drone (RC serial number). */
export function manualSocketFor(sn: string): ManualSocket {
  let s = sockets.get(sn)
  if (!s) {
    s = new ManualSocket(sn)
    sockets.set(sn, s)
  }
  return s
}
