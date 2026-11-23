import { describe, expect, it } from 'vitest'
import { fromDisplay, gcj02ToWgs84, toDisplay, wgs84ToGcj02 } from '@/utils/coord'
import { distance, pointInPolygon } from '@/utils/geo'

describe('coordinate conversion (Q-06)', () => {
  it('applies a GCJ-02 offset inside China and round-trips to WGS84', () => {
    const wgs = { lat: 22.58, lon: 113.94 }
    const g = wgs84ToGcj02(wgs.lat, wgs.lon)
    const offset = distance(wgs, g)
    expect(offset).toBeGreaterThan(200)
    expect(offset).toBeLessThan(800)
    const back = gcj02ToWgs84(g.lat, g.lon)
    expect(distance(wgs, back)).toBeLessThan(0.05)
  })

  it('leaves coordinates outside China untouched', () => {
    expect(wgs84ToGcj02(48.85, 2.35)).toEqual({ lat: 48.85, lon: 2.35 })
  })

  it('only converts at the display boundary when the base map is GCJ-02', () => {
    const p = { lat: 30.5, lon: 114.3 }
    expect(toDisplay(p, 'WGS84')).toEqual(p)
    const shown = toDisplay(p, 'GCJ02')
    expect(distance(fromDisplay(shown, 'GCJ02'), p)).toBeLessThan(0.05)
  })
})

describe('GCJ-02 base maps (D-17)', () => {
  it('round-trips display <-> platform coordinates within a centimetre across China', () => {
    const points = [
      { lat: 22.58, lon: 113.94 },
      { lat: 39.9087, lon: 116.3975 },
      { lat: 31.2304, lon: 121.4737 },
      { lat: 43.8256, lon: 87.6168 },
      { lat: 18.25, lon: 109.5 },
    ]
    for (const p of points) {
      const shown = toDisplay(p, 'GCJ02')
      expect(distance(shown, p)).toBeGreaterThan(50)
      expect(distance(fromDisplay(shown, 'GCJ02'), p)).toBeLessThan(0.01)
    }
  })
})

describe('geo helpers', () => {
  it('detects points inside a polygon', () => {
    const square = [
      { lat: 0, lon: 0 },
      { lat: 0, lon: 1 },
      { lat: 1, lon: 1 },
      { lat: 1, lon: 0 },
    ]
    expect(pointInPolygon({ lat: 0.5, lon: 0.5 }, square)).toBe(true)
    expect(pointInPolygon({ lat: 1.5, lon: 0.5 }, square)).toBe(false)
  })
})
