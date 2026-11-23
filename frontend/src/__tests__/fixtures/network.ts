import { defaultNetworkConfig } from '@/network/config'
import type { ConnectionMode, NetworkSnapshot } from '@/network/types'
// @ts-expect-error plain JavaScript development fixture; all data in this module is fabricated for tests.
import { makeSnapshot } from '../../../../scripts/network-studio/mock.mjs'

export function networkConfig(enabled = true, mode: ConnectionMode = 'server') {
  return { ...defaultNetworkConfig(), enabled, mode }
}
/** Declared measured solely to test the real-workspace boundary. NOT field measurements. */
export function declaredMeasuredFixture(at = 100000): NetworkSnapshot {
  const s = makeSnapshot({ at }) as NetworkSnapshot
  return { ...s, provenance: 'measured', instanceId: 'test-server', sourceId: 'test-receiver', nodes: s.nodes.map(n => ({ ...n,
    position: n.position ? { ...n.position, source: 'test-declared-gnss' } : null,
  })) }
}
export function legacyGatewayFixture() {
  return { schema: 'lora.topology.v1', source: 'gateway_udp_lrn1', source_id: 'test-gateway', selection_epoch: 2,
    labels: { '02:00:00:01:00:01': '1', '02:00:00:01:00:02': '2' },
    receiver: { gateway_id: 'test-gateway-eui', gateway_observed: true, state: 'receiving', recent_threshold_ms: 30000, frames: 12 },
    reports: [{ pc_receive_age_ms: 500, gps_age_ms: 1500, status_age_ms: 500,
      gps: { valid: true, lat_e7: 400010000, lon_e7: 1163260000 }, status: { battery_pct: 83 },
      lora: { rssi: -88, lsnr: 7.5, freq: 470.5, chan: 1 },
      report: { frame_schema: 'LRN1', observer_id: '02:00:00:01:00:01', report_period_ms: 10000,
        neighbors: [{ peer_id: '02:00:00:01:00:02', state: 'bidirectional', valid: 15, seen_age_ms: 200, ack_age_ms: 100, rssi_dbm: -65, rf_age_ms: 200, wifi_channel: 6 }] },
    }],
  }
}
export const measuredCapabilities = { schema: 'network.capabilities.v1', mock: false, recording: false, sourceSelection: false,
  sources: [{ id: 'test-receiver', label: 'Test receiver (intercepted)' }], selectedSourceId: 'test-receiver', scenario: null }
