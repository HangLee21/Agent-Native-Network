/**
 * WGS84 <-> GCJ-02 conversion (research-notes Q-06). Platform data and everything sent to the
 * aircraft stays WGS84; conversion happens only at the map display/pick boundary when the
 * configured base map uses GCJ-02.
 */
import type { CoordSys } from '@/config/runtime'

const A = 6378245.0
const EE = 0.006693421622965943

export interface LatLon {
  lat: number
  lon: number
}

/** GCJ-02 offsets apply only inside mainland China (rough bounding box, as commonly used). */
export function outOfChina(lat: number, lon: number): boolean {
  return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function transformLat(x: number, y: number): number {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin((y / 3.0) * Math.PI)) * 2.0) / 3.0
  ret += ((160.0 * Math.sin((y / 12.0) * Math.PI) + 320 * Math.sin((y * Math.PI) / 30.0)) * 2.0) / 3.0
  return ret
}

function transformLon(x: number, y: number): number {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin((x / 3.0) * Math.PI)) * 2.0) / 3.0
  ret += ((150.0 * Math.sin((x / 12.0) * Math.PI) + 300.0 * Math.sin((x / 30.0) * Math.PI)) * 2.0) / 3.0
  return ret
}

export function wgs84ToGcj02(lat: number, lon: number): LatLon {
  if (outOfChina(lat, lon)) return { lat, lon }
  let dLat = transformLat(lon - 105.0, lat - 35.0)
  let dLon = transformLon(lon - 105.0, lat - 35.0)
  const radLat = (lat / 180.0) * Math.PI
  let magic = Math.sin(radLat)
  magic = 1 - EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  dLat = (dLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * Math.PI)
  dLon = (dLon * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * Math.PI)
  return { lat: lat + dLat, lon: lon + dLon }
}

/** Iterative inverse (sub-centimetre after a few iterations). */
export function gcj02ToWgs84(lat: number, lon: number): LatLon {
  if (outOfChina(lat, lon)) return { lat, lon }
  let wLat = lat
  let wLon = lon
  for (let i = 0; i < 6; i++) {
    const g = wgs84ToGcj02(wLat, wLon)
    wLat += lat - g.lat
    wLon += lon - g.lon
  }
  return { lat: wLat, lon: wLon }
}

/** Platform (WGS84) -> base map coordinates. */
export function toDisplay(p: LatLon, sys: CoordSys): LatLon {
  return sys === 'GCJ02' ? wgs84ToGcj02(p.lat, p.lon) : { lat: p.lat, lon: p.lon }
}

/** Base map coordinates (user click) -> platform (WGS84). */
export function fromDisplay(p: LatLon, sys: CoordSys): LatLon {
  return sys === 'GCJ02' ? gcj02ToWgs84(p.lat, p.lon) : { lat: p.lat, lon: p.lon }
}
