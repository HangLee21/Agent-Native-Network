import { describe, expect, it } from 'vitest'
import { resolveConfig } from '@/config/runtime'

describe('runtime config (C-08: separate deployment)', () => {
  it('uses configured backend URLs as-is', () => {
    const cfg = resolveConfig({ apiBaseUrl: 'https://uav.example.org/', wsUrl: 'wss://uav.example.org/ws/telemetry' }, 'http://frontend.local')
    expect(cfg.apiBaseUrl).toBe('https://uav.example.org')
    expect(cfg.wsUrl).toBe('wss://uav.example.org/ws/telemetry')
  })

  it('falls back to the page origin for same-host deployment', () => {
    const cfg = resolveConfig({}, 'http://10.0.0.5:8080')
    expect(cfg.apiBaseUrl).toBe('http://10.0.0.5:8080')
    expect(cfg.wsUrl).toBe('ws://10.0.0.5:8080/ws/telemetry')
    expect(cfg.map.coordSys).toBe('WGS84')
  })

  it('turns an old single-tile map config into one base map that behaves as before', () => {
    const cfg = resolveConfig(
      {
        map: {
          coordSys: 'GCJ02',
          tileUrl: 'https://tiles.example.org/{s}/{z}/{x}/{y}.png?key={key}',
          subdomains: '12',
          attribution: 'Example',
          maxZoom: 17,
          apiKey: 'k',
        } as never,
      },
      'http://x',
    )
    expect(cfg.map.baseMaps).toEqual([
      {
        id: 'configured',
        label: '配置底图',
        coordSys: 'GCJ02',
        tiles: [{ url: 'https://tiles.example.org/{s}/{z}/{x}/{y}.png?key={key}', subdomains: '12', maxZoom: 17, attribution: 'Example' }],
      },
    ])
    expect(cfg.map.defaultBaseMap).toBe('configured')
    expect(cfg.map.apiKey).toBe('k')
  })

  it('offers Gaode street, Gaode satellite and OSM by default, Gaode street first', () => {
    const cfg = resolveConfig({}, 'http://x')
    expect(cfg.map.baseMaps.map((b) => [b.id, b.coordSys])).toEqual([
      ['gaode-street', 'GCJ02'],
      ['gaode-satellite', 'GCJ02'],
      ['osm', 'WGS84'],
    ])
    expect(cfg.map.defaultBaseMap).toBe('gaode-street')
    expect(cfg.map.baseMaps[1]!.tiles).toHaveLength(2)
  })

  it('uses configured base maps and repairs an unknown default', () => {
    const baseMaps = [{ id: 'a', label: 'A', coordSys: 'WGS84' as const, tiles: [{ url: 'https://a/{z}/{x}/{y}.png' }] }]
    const cfg = resolveConfig({ map: { baseMaps, defaultBaseMap: 'missing' } as never }, 'http://x')
    expect(cfg.map.baseMaps).toEqual(baseMaps)
    expect(cfg.map.defaultBaseMap).toBe('a')
  })
})
