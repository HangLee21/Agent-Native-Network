/** Small-distance geometry for the demo pages (same approximations as the backend's Geo). */
import type { LatLon } from './demoApi'

const R = 6371008.8
const rad = (d: number) => (d * Math.PI) / 180

export function distanceM(a: LatLon, b: LatLon): number {
  const dLat = rad(b.lat - a.lat)
  const dLon = rad(b.lon - a.lon)
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)))
}

/** Compass bearing from `a` to `b`, degrees. */
export function bearingDeg(a: LatLon, b: LatLon): number {
  const p1 = rad(a.lat)
  const p2 = rad(b.lat)
  const dl = rad(b.lon - a.lon)
  const y = Math.sin(dl) * Math.cos(p2)
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
  return (Math.atan2(y, x) * 180) / Math.PI
}

/** North / east metres of `p` from `origin`. */
export function toLocal(origin: LatLon, p: LatLon): { n: number; e: number } {
  return { n: rad(p.lat - origin.lat) * R, e: rad(p.lon - origin.lon) * R * Math.cos(rad(origin.lat)) }
}

export function offset(p: LatLon, n: number, e: number): LatLon {
  return { lat: p.lat + (n / R) * (180 / Math.PI), lon: p.lon + (e / (R * Math.cos(rad(p.lat)))) * (180 / Math.PI) }
}

/** Point `dist` metres from `p` towards compass bearing `deg`. */
export function project(p: LatLon, deg: number, dist: number): LatLon {
  return offset(p, dist * Math.cos(rad(deg)), dist * Math.sin(rad(deg)))
}

export interface CameraPose {
  lat: number
  lon: number
  /** Camera height above the ground (relative to take-off), metres. */
  height: number
  /** Compass yaw of the camera (aircraft heading + gimbal yaw), degrees. */
  yaw: number
  /** Gimbal pitch, degrees (negative = looking down). */
  pitch: number
}

/** Horizontal field of view of the wide lens assumed for overlays (same as the mock feed). */
export const WIDE_HFOV_DEG = 72

/**
 * Projects a ground point (height `up` above take-off level) into the frame, normalised 0..1 from the top-left,
 * with a pinhole camera of the given pose; null when it is behind the camera. Approximate: no lens distortion,
 * flat ground, no aircraft roll / pitch.
 */
export function projectToFrame(cam: CameraPose, p: LatLon, up = 0, aspect = 16 / 9, hfov = WIDE_HFOV_DEG): { x: number; y: number } | null {
  const { n, e } = toLocal(cam, p)
  const yaw = rad(cam.yaw)
  const pitch = rad(cam.pitch)
  const fwd = n * Math.cos(yaw) + e * Math.sin(yaw)
  const right = -n * Math.sin(yaw) + e * Math.cos(yaw)
  const rel = up - cam.height
  const fz = fwd * Math.cos(pitch) + rel * Math.sin(pitch)
  const uz = -fwd * Math.sin(pitch) + rel * Math.cos(pitch)
  if (fz < 0.5) return null
  const tanH = Math.tan(rad(hfov / 2))
  const tanV = tanH / aspect
  return { x: 0.5 + right / fz / tanH / 2, y: 0.5 - uz / fz / tanV / 2 }
}
