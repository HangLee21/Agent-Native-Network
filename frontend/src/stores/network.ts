import { computed, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { loadNetworkConfig, NetworkClient } from '@/network/api'
import { nodeState } from '@/network/model'
import type { EngineeringStatus } from '@/network/legacy'
import { defaultNetworkConfig, parseNetworkConfig, savedConnections, saveConnections, validateProfile } from '@/network/config'
import type { ConnectionMode, ConnectionProfile, MockScenario, NetworkCapabilities, NetworkConfig, NetworkNode, NetworkSnapshot, NodeTag, ReplayData, ReplaySummary, Workspace } from '@/network/types'

/** A platform-wide observer, deliberately independent of selected drone and all command stores. */
export const useNetworkStore = defineStore('network', () => {
  const workspace = ref<Workspace>('real')
  const configuration = shallowRef<NetworkConfig>(defaultNetworkConfig())
  const profile = computed(() => configuration.value.profiles[configuration.value.mode])
  const connectionKey = computed(() => `${workspace.value}:${configuration.value.mode}:${profile.value.protocol}:${new URL(profile.value.apiBaseUrl || '/', location.origin).href}`)
  const snapshot = shallowRef<NetworkSnapshot | null>(null)
  const tags = ref<Record<string, NodeTag>>({})
  const tagKey = computed(() => `network.tags.v2:${connectionKey.value}:${snapshot.value?.sourceId ?? ''}`)
  watch(tagKey, key => {
    try {
      const raw: unknown = JSON.parse(localStorage.getItem(key) || '{}')
      tags.value = raw && typeof raw === 'object' && !Array.isArray(raw) ? Object.fromEntries(Object.entries(raw).filter(([, v]) => ['node', 'drone', 'robot'].includes(v))) : {}
    } catch { tags.value = {} }
  }, { immediate: true, flush: 'sync' })
  const tagOf = (n: NetworkNode): NodeTag => Object.prototype.hasOwnProperty.call(tags.value, n.id) ? tags.value[n.id]! : n.tag ?? 'node'
  const displaySnapshot = computed(() => snapshot.value ? { ...snapshot.value, nodes: snapshot.value.nodes.map(n => ({ ...n, tag: tagOf(n) })) } : null)
  function setTag(id: string, tag: NodeTag) {
    if (!['node', 'drone', 'robot'].includes(tag) || !snapshot.value?.nodes.some(n => n.id === id && n.role !== 'gateway')) return
    tags.value = { ...tags.value, [id]: tag }
    try { localStorage.setItem(tagKey.value, JSON.stringify(tags.value)) } catch { /* optional */ }
  }
  const capabilities = shallowRef<NetworkCapabilities | null>(null)
  const engineeringStatus = shallowRef<EngineeringStatus | null>(null)
  const status = ref<'connecting' | 'online' | 'error' | 'disabled'>('connecting')
  const error = ref('')
  const paused = ref(false)
  const busy = ref(false)
  const mode = ref<'live' | 'replay'>('live')
  const observationLayer = ref<'lora' | 'wifi'>('lora')
  const clock = ref(Date.now())
  const receivedAt = ref(0)
  const sessions = ref<ReplaySummary[]>([])
  const replay = shallowRef<ReplayData | null>(null)
  const frame = ref(0)
  const replayTotal = computed(() => replay.value?.total ?? replay.value?.frames.length ?? 0)
  let seekSequence = 0
  let playbackSequence = 0
  const playing = ref(false)
  const speed = ref(1)
  const recording = ref<string | null>(null)
  let client: NetworkClient | null = null
  let generation = 0
  let active = false
  let polling: ReturnType<typeof setTimeout> | undefined
  let ticking: ReturnType<typeof setInterval> | undefined
  let playback: ReturnType<typeof setTimeout> | undefined
  let pending: AbortController | null = null
  let refreshing = false

  const now = computed(() => mode.value === 'replay' ? snapshot.value?.observedAt ?? clock.value :
    snapshot.value ? snapshot.value.observedAt + Math.max(0, clock.value - receivedAt.value) : clock.value)
  const interrupted = computed(() => mode.value === 'live' && (status.value === 'error' || (!paused.value && !!snapshot.value && clock.value - receivedAt.value > 7000)))
  const recent = computed(() => snapshot.value?.nodes.filter(n => n.role !== 'gateway' && nodeState(n, snapshot.value!, now.value, interrupted.value) === 'recent').length ?? 0)
  const canPoll = () => active && !document.hidden && !paused.value && mode.value === 'live' && !!client && status.value !== 'disabled'
  const message = (e: unknown) => e instanceof Error ? e.message : 'NETWORK_REQUEST_FAILED'
  function cancelRequest() { generation++; pending?.abort(); pending = null; refreshing = false; busy.value = false; clearTimeout(polling) }
  function schedule() { clearTimeout(polling); if (canPoll()) polling = setTimeout(() => void refresh(), 2000) }
  function stopPlayback() { clearTimeout(playback); playing.value = false; playbackSequence++ }
  function syncEngineering() {
    if (!client?.engineering) return
    engineeringStatus.value = { ...client.engineering.state }
    if (client.engineering.state.available) { capabilities.value = client.engineering.capabilities(); recording.value = client.engineering.state.recordingId }
  }
  async function readEvidence(after = 0, signal?: AbortSignal) {
    if (!active || !client || mode.value !== 'live' || paused.value || document.hidden) throw new Error('BASELINE_EVIDENCE_LIVE_ONLY')
    return client.evidence(after, signal)
  }

  async function refresh(): Promise<void> {
    if (!canPoll() || refreshing) return
    const ticket = generation
    const controller = new AbortController()
    pending = controller; refreshing = true
    const timeout = setTimeout(() => controller.abort(), 6000)
    try {
      const value = observationLayer.value === 'wifi' ? await client!.wifiSnapshot(controller.signal) : await client!.snapshot(controller.signal)
      if (ticket !== generation || !active) return
      const old = snapshot.value
      if (old && old.instanceId === value.instanceId && old.sourceId === value.sourceId && value.epoch < old.epoch) throw new Error('NETWORK_EPOCH_REGRESSION')
      snapshot.value = value; receivedAt.value = Date.now(); clock.value = receivedAt.value; syncEngineering()
      status.value = 'online'; error.value = ''
    } catch (e) {
      if (ticket === generation && active) { status.value = 'error'; error.value = message(e) }
    } finally {
      clearTimeout(timeout)
      if (ticket === generation) { refreshing = false; pending = null; schedule() }
    }
  }
  async function loadSessions() {
    const ticket = generation
    try {
      if (!client) return
      const result = await client.sessions()
      if (active && ticket === generation) { sessions.value = result; syncEngineering() }
    } catch (e) { if (active && ticket === generation) error.value = message(e) }
  }
  async function start(target: Workspace = 'real', override?: NetworkConfig) {
    if (active && workspace.value === target) return
    if (active) stop()
    workspace.value = target
    active = true; paused.value = false; mode.value = 'live'; observationLayer.value = 'lora'; status.value = 'connecting'; error.value = ''
    busy.value = false; client = null; snapshot.value = null; capabilities.value = null; engineeringStatus.value = null; sessions.value = []; replay.value = null; recording.value = null; receivedAt.value = 0
    document.addEventListener('visibilitychange', visibility)
    ticking = setInterval(() => { if (!document.hidden) clock.value = Date.now() }, 1000)
    const ticket = ++generation
    try {
      const loaded = override ?? await loadNetworkConfig(target)
      if (ticket !== generation || !active) return
      const config = override || target === 'mock' ? loaded : savedConnections(loaded)
      configuration.value = config
      if (!config.enabled) { status.value = 'disabled'; return }
      const selectedProfile = config.profiles[config.mode]
      const candidate = new NetworkClient(selectedProfile.apiBaseUrl, { workspace: target, mode: config.mode, protocol: selectedProfile.protocol, gatewayRelayPath: config.gatewayRelayPath, engineeringRelayPath: config.engineeringRelayPath })
      const controller = new AbortController()
      pending = controller
      const timeout = setTimeout(() => controller.abort(), 6000)
      let caps: NetworkCapabilities
      try { caps = await candidate.capabilities(controller.signal) }
      finally { clearTimeout(timeout); if (pending === controller) pending = null }
      if (ticket !== generation || !active) return
      client = candidate; capabilities.value = caps
      await refresh(); if (active && ticket === generation) await loadSessions()
    } catch (e) { if (ticket === generation && active) { status.value = 'error'; error.value = message(e); schedule() } }
  }
  function stop() {
    active = false; cancelRequest(); stopPlayback(); clearInterval(ticking)
    document.removeEventListener('visibilitychange', visibility)
  }
  function disconnect() {
    stop(); client = null; snapshot.value = null; capabilities.value = null; engineeringStatus.value = null; sessions.value = []; replay.value = null
    recording.value = null; mode.value = 'live'; status.value = 'disabled'; paused.value = false; error.value = ''
    configuration.value = { ...configuration.value, enabled: false }
  }
  function selectConnectionMode(value: ConnectionMode) {
    if (workspace.value !== 'real' || !['server', 'gateway'].includes(value)) return
    disconnect(); configuration.value = { ...configuration.value, mode: value }; saveConnections(configuration.value)
  }
  async function connect(value: ConnectionMode, input: ConnectionProfile) {
    if (workspace.value !== 'real') return
    disconnect()
    try {
      const checked = validateProfile(input, value)
      const next = parseNetworkConfig({ ...configuration.value, enabled: true, mode: value,
        profiles: { ...configuration.value.profiles, [value]: checked } })
      saveConnections(next); await start('real', next)
    } catch (e) { status.value = 'error'; error.value = message(e) }
  }
  function visibility() {
    if (document.hidden) { cancelRequest(); stopPlayback() }
    else if (active && !client && status.value !== 'disabled') {
      const target = workspace.value, config = configuration.value
      stop(); void start(target, config.enabled ? config : undefined)
    } else if (canPoll()) { clock.value = Date.now(); void refresh() }
  }
  function togglePause() {
    if (!active || !client) return
    paused.value = !paused.value
    if (paused.value) cancelRequest()
    else { clock.value = Date.now(); void refresh() }
  }
  async function mutate(operation: () => Promise<NetworkCapabilities>) {
    if (busy.value || !client || mode.value !== 'live') return
    cancelRequest(); busy.value = true
    const ticket = generation
    try {
      const result = await operation()
      if (!active || ticket !== generation) return
      capabilities.value = result; snapshot.value = null; status.value = 'connecting'; error.value = ''
      // Explicit changes take effect even if the observer was paused; resume is visible in the UI.
      paused.value = false; await refresh()
    } catch (e) { if (active && ticket === generation) { error.value = message(e); status.value = 'error' } }
    finally { if (ticket === generation) { busy.value = false; schedule() } }
  }
  async function selectObservationLayer(layer: 'lora' | 'wifi') {
    if (!active || !client || !capabilities.value?.engineering || busy.value || mode.value !== 'live' || layer === observationLayer.value) return
    cancelRequest(); stopPlayback(); observationLayer.value = layer; snapshot.value = null; paused.value = false; status.value = 'connecting'; error.value = ''
    await refresh()
  }
  function selectSource(id: string) {
    if (!capabilities.value?.sourceSelection) return Promise.resolve()
    return mutate(() => client!.selectSource(id))
  }
  function setScenario(scenario: MockScenario) {
    if (!capabilities.value?.mock) return Promise.resolve()
    return mutate(() => client!.setScenario(scenario))
  }
  async function openReplay(id: string) {
    if (!client || busy.value || recording.value) return
    cancelRequest(); busy.value = true; stopPlayback()
    const ticket = generation
    try {
      const result = await client.replay(id)
      if (!active || ticket !== generation) return
      if (!result.frames.length) throw new Error('NETWORK_REPLAY_EMPTY')
      replay.value = result; mode.value = 'replay'; frame.value = 0; snapshot.value = result.frames[0]!
      status.value = 'online'; error.value = ''
    } catch (e) { if (active && ticket === generation) { error.value = message(e); schedule() } }
    finally { if (ticket === generation) busy.value = false }
  }
  async function seek(index: number, duringPlayback = false) {
    if (!replay.value?.frames.length || !Number.isFinite(index)) return
    if (!duringPlayback) stopPlayback()
    const target = Math.max(0, Math.min(replayTotal.value - 1, Math.round(index)))
    const offset = replay.value.offset ?? 0
    if (target >= offset && target < offset + replay.value.frames.length) {
      frame.value = target; snapshot.value = replay.value.frames[target - offset]!; return
    }
    if (!replay.value.paginated || !client) return
    const ticket = generation, sequence = ++seekSequence, id = replay.value.id
    busy.value = true
    try {
      const result = await client.replay(id, Math.floor(target / 25) * 25)
      if (!active || ticket !== generation || sequence !== seekSequence || mode.value !== 'replay' || replay.value?.id !== id) return
      const next = result.frames[target - (result.offset ?? 0)]
      if (!next) throw new Error('NETWORK_REPLAY_FRAME_UNAVAILABLE')
      replay.value = result; frame.value = target; snapshot.value = next; error.value = ''
    } catch (e) { if (active && ticket === generation && sequence === seekSequence) { error.value = message(e); stopPlayback() } }
    finally { if (ticket === generation && sequence === seekSequence) busy.value = false }
  }
  async function play() {
    if (playing.value) { stopPlayback(); return }
    if (!replay.value?.frames.length || mode.value !== 'replay' || busy.value) return
    const ticket = generation
    if (frame.value >= replayTotal.value - 1) await seek(0)
    if (!active || ticket !== generation || mode.value !== 'replay' || error.value) return
    playing.value = true; void schedulePlayback()
  }
  async function schedulePlayback() {
    const data = replay.value, ticket = generation, sequence = playbackSequence, started = Date.now(), index = frame.value
    const current = data?.frames[index - (data.offset ?? 0)]
    let next = data?.frames[index + 1 - (data.offset ?? 0)], page: ReplayData | undefined
    if (!playing.value || !data || !current || index >= replayTotal.value - 1) { stopPlayback(); return }
    try {
      if (!next && data.paginated && client) { page = await client.replay(data.id, index + 1); next = page.frames[0] }
      if (!playing.value || !active || ticket !== generation || sequence !== playbackSequence || mode.value !== 'replay') return
      if (!next || next.observedAt < current.observedAt) throw new Error('NETWORK_REPLAY_ORDER_INVALID')
      const delay = Math.max(16, (next.observedAt - current.observedAt) / speed.value - (Date.now() - started))
      playback = setTimeout(() => {
        if (page) replay.value = page
        void seek(index + 1, true)
        if (index + 1 >= replayTotal.value - 1) stopPlayback(); else void schedulePlayback()
      }, delay)
    } catch (e) { if (active && ticket === generation && sequence === playbackSequence) { error.value = message(e); stopPlayback() } }
  }
  function setSpeed(value: number) {
    speed.value = [1, 2, 4].includes(value) ? value : 1
    if (playing.value) { stopPlayback(); play() }
  }
  async function goLive() {
    cancelRequest(); stopPlayback(); mode.value = 'live'; replay.value = null; snapshot.value = null; paused.value = false
    status.value = 'connecting'; await refresh()
  }
  async function toggleRecording() {
    if (!client || !capabilities.value?.recording || busy.value || mode.value !== 'live' || (observationLayer.value !== 'lora' && !recording.value)) return
    busy.value = true
    const ticket = generation
    try { const r = await client.record(recording.value ? 'stop' : 'start'); if (active && ticket === generation) { recording.value = r.id; await loadSessions() } }
    catch (e) { if (active && ticket === generation) error.value = message(e) }
    finally { if (ticket === generation) busy.value = false }
  }
  async function retry() {
    if (!client) { const target = workspace.value, config = configuration.value; stop(); await start(target, config.enabled ? config : undefined) }
    else { paused.value = false; await refresh() }
  }
  return { workspace, configuration, profile, connectionKey, displaySnapshot, tagOf, setTag, connect, disconnect, selectConnectionMode,
    snapshot, capabilities, engineeringStatus, readEvidence, status, error, paused, busy, mode, now, receivedAt, interrupted, recent, sessions, replay, replayTotal, frame, playing, speed, recording,
    observationLayer, selectObservationLayer, start, stop, refresh, retry, togglePause, selectSource, setScenario, loadSessions, openReplay, seek, play, setSpeed, goLive, toggleRecording }
})
