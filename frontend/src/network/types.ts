/** Network observations only. Never used by the flight-control or fleet-safety stores. */
export type NodeRole = 'gateway' | 'node' | 'aircraft' | 'robot' | 'relay'
export type NodeTag = 'node' | 'drone' | 'robot'
export type Workspace = 'real' | 'mock'
export type ConnectionMode = 'server' | 'gateway'
export type NetworkProtocol = 'network-v1' | 'lora-v1'
export type LinkKind = 'wifi' | 'lora'
export type LayoutMode = 'clear' | 'manual' | 'gps'
export type ObservationState = 'recent' | 'stale' | 'unknown' | 'interrupted'
export interface NetworkPosition { lat: number; lon: number; observedAt: number; source: string }
export interface NetworkNode {
  id: string; label: string; role: NodeRole; reportedAt: number | null
  tag?: NodeTag
  position: NetworkPosition | null; batteryPercent: number | null
  radio: { rssiDbm: number | null; snrDb: number | null; channel: number | null; frequencyHz: number | null }
  binding: { kind: 'drone' | 'dog'; id: string } | null
}
export interface NetworkLink {
  id: string; from: string; to: string; kind: LinkKind
  state: 'mutual' | 'oneway' | 'lost' | 'unknown'
  sampledAt: number | null; validForMs: number | null
  rssiDbm: number | null; snrDb: number | null; channel: number | null
}
export interface NetworkEvent {
  id: string; at: number; kind: 'report' | 'link' | 'receiver'; nodeId: string | null
  code: 'report_received' | 'link_changed' | 'receiver_recovered' | 'receiver_interrupted'
}
export interface NetworkSnapshot {
  schema: 'network.snapshot.v1'; provenance: 'synthetic' | 'measured' | 'unknown'
  instanceId: string; sourceId: string; epoch: number; observedAt: number; reportTimeoutMs: number
  receiver: { id: string; label: string; state: 'receiving' | 'waiting' | 'unavailable'; receivedCount: number }
  nodes: NetworkNode[]; links: NetworkLink[]; events: NetworkEvent[]
}
export interface NetworkSource { id: string; label: string }
export type MockScenario = 'nominal' | 'dense' | 'empty' | 'interrupted' | 'stale' | 'no-gps'
export interface NetworkCapabilities {
  schema: 'network.capabilities.v1'; mock: boolean; recording: boolean; sourceSelection: boolean
  sources: NetworkSource[]; selectedSourceId: string; scenario: MockScenario | null
}
export interface ReplaySummary { id: string; label: string; startedAt: number; frames: number; synthetic: boolean }
export interface ReplayData { schema: 'network.replay.v1'; id: string; frames: NetworkSnapshot[] }
export interface ConnectionProfile { apiBaseUrl: string; protocol: NetworkProtocol }
export interface NetworkConfig {
  schema: 'network.config.v2'; enabled: boolean; mode: ConnectionMode
  profiles: Record<ConnectionMode, ConnectionProfile>
  gatewayRelayPath?: string
}
export interface Point { x: number; y: number }
