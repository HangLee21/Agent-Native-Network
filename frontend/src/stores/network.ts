import { computed, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { loadNetworkConfig, NetworkClient } from '@/network/api'
import { nodeState } from '@/network/model'
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
  const status = ref<'connecting' | 'online' | 'error' | 'disabled'>('connecting')
  const error = ref('')
  const paused = ref(false)
  const busy = ref(false)
  const mode = ref<'live' | 'replay'>('live')
  const clock = ref(Date.now())
  const receivedAt = ref(0)
  const sessions = ref<ReplaySummary[]>([])
  const replay = shallowRef<ReplayData | null>(null)
  const frame = ref(0)
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
  function stopPlayback() { clearTimeout(playback); playing.value = false }

  async function refresh(): Promise<void> {
    if (!canPoll() || refreshing) return
    const ticket = generation
    const controller = new AbortController()
    pending = controller; refreshing = true
    const timeout = setTimeout(() => controller.abort(), 6000)
    try {
      const value = await client!.snapshot(controller.signal)
      if (ticket !== generation || !active) return
      const old = snapshot.value
      if (old && old.instanceId === value.instanceId && old.sourceId === value.sourceId && value.epoch < old.epoch) throw new Error('NETWORK_EPOCH_REGRESSION')
      snapshot.value = value; receivedAt.value = Date.now(); clock.value = receivedAt.value
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
      if (active && ticket === generation) sessions.value = result
    } catch (e) { if (active && ticket === generation) error.value = message(e) }
  }
  async function start(target: Workspace = 'real', override?: NetworkConfig) {
    if (active && workspace.value === target) return
    if (active) stop()
    workspace.value = target
    active = true; paused.value = false; mode.value = 'live'; status.value = 'connecting'; error.value = ''
    busy.value = false; client = null; snapshot.value = null; capabilities.value = null; sessions.value = []; replay.value = null; recording.value = null; receivedAt.value = 0
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
      const candidate = new NetworkClient(selectedProfile.apiBaseUrl, { workspace: target, mode: config.mode, protocol: selectedProfile.protocol, gatewayRelayPath: config.gatewayRelayPath })
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
    stop(); client = null; snapshot.value = null; capabilities.value = null; sessions.value = []; replay.value = null
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
  function seek(index: number, duringPlayback = false) {
    if (!replay.value?.frames.length) return
    if (!duringPlayback) stopPlayback()
    frame.value = Math.max(0, Math.min(replay.value.frames.length - 1, Math.round(index)))
    snapshot.value = replay.value.frames[frame.value]!
  }
  function play() {
    if (playing.value) { stopPlayback(); return }
    if (!replay.value?.frames.length || mode.value !== 'replay') return
    if (frame.value >= replay.value.frames.length - 1) seek(0)
    playing.value = true
    schedulePlayback()
  }
  function schedulePlayback() {
    const frames = replay.value?.frames, current = frames?.[frame.value], next = frames?.[frame.value + 1]
    if (!playing.value || !current || !next) { stopPlayback(); return }
    // Preserve captured timing: a 2-second observation interval is 2 seconds at 1x, not 1 second.
    playback = setTimeout(() => { seek(frame.value + 1, true); schedulePlayback() }, Math.max(16, next.observedAt - current.observedAt) / speed.value)
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
    if (!client || !capabilities.value?.recording || busy.value || mode.value !== 'live') return
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
    snapshot, capabilities, status, error, paused, busy, mode, now, receivedAt, interrupted, recent, sessions, replay, frame, playing, speed, recording,
    start, stop, refresh, retry, togglePause, selectSource, setScenario, loadSessions, openReplay, seek, play, setSpeed, goLive, toggleRecording }
})
