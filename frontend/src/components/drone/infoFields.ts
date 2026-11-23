/** Field groups for the full information panel (R-05). Labels follow the M4 / RC Plus 2 property pages. */
import type { DroneTelemetry, RcTelemetry } from '@/api/types'
import { GEAR_LABELS, WIND_DIRECTIONS, coord, dateTime, duration, modeLabel, num } from '@/utils/format'
import { t } from '@/i18n'

export interface InfoRow {
  label: string
  value: string
  hint?: string
}

export interface InfoGroup {
  title: string
  rows: InfoRow[]
}

type Raw = Record<string, unknown>

function obj(v: unknown): Raw {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Raw) : {}
}
function n(v: unknown): number | null {
  return typeof v === 'number' ? v : null
}
function s(v: unknown): string {
  return v === null || v === undefined || v === '' ? '—' : String(v)
}
function onOff(v: unknown): string {
  return v === 1 || v === true ? t('开启') : v === 0 || v === false ? t('关闭') : '—'
}

export function droneGroups(d: DroneTelemetry | null, rc: RcTelemetry | null): InfoGroup[] {
  const raw: Raw = d?.raw ?? {}
  const battery = obj(raw.battery)
  const pos = obj(raw.position_state)
  const obstacle = obj(raw.obstacle_avoidance)
  const storage = obj(raw.storage)
  const rcRaw: Raw = rc?.raw ?? {}
  const link = obj(rcRaw.wireless_link)
  const batteries = Array.isArray(battery.batteries) ? (battery.batteries as Raw[]) : []
  const groups: InfoGroup[] = [
    {
      title: t('飞行状态'),
      rows: [
        { label: t('飞行器状态'), value: d ? modeLabel(d.modeCode) : '—' },
        { label: t('档位'), value: d?.gear != null ? (GEAR_LABELS[d.gear] ?? String(d.gear)) : '—' },
        { label: t('控制源'), value: s(d?.controlSource), hint: t('A/B 表示 A 控/B 控，浏览器为 uuid') },
        { label: t('航迹 ID'), value: s(d?.trackId) },
        { label: t('返航高度模式'), value: raw.rth_mode === 0 ? t('智能高度') : raw.rth_mode === 1 ? t('设定高度') : '—' },
        // M4E reports the return height in effect, also one the pilot changed in Pilot 2 (field test 2026-11-04)
        { label: t('返航高度'), value: num(n(raw.rth_altitude), 0, 'm'), hint: t('飞行器上报（rth_altitude），相对起飞点') },
        { label: t('指点飞行高度'), value: num(n(raw.commander_flight_height), 1, 'm'), hint: t('相对起飞点') },
        { label: t('指点飞行失控动作'), value: raw.commander_mode_lost_action === 0 ? t('继续执行') : raw.commander_mode_lost_action === 1 ? t('退出并执行普通失控行为') : '—' },
      ],
    },
    {
      title: t('位置与高度'),
      rows: [
        // no position while the drone has no satellites (the 0/0 it reports is dropped by the backend)
        { label: t('纬度'), value: d && d.lat == null ? t('定位中') : coord(d?.lat) },
        { label: t('经度'), value: d && d.lon == null ? t('定位中') : coord(d?.lon) },
        { label: t('相对起飞点高度'), value: num(d?.relativeHeight, 1, 'm'), hint: 'elevation' },
        { label: t('椭球高'), value: num(d?.ellipsoidHeight, 1, 'm'), hint: t('height（WGS84 椭球面）') },
        { label: t('DRC 高度'), value: num(n(raw.drc_height), 1), hint: t('椭球高') },
        { label: t('Home 点'), value: d?.homeLat != null ? `${coord(d.homeLat)}, ${coord(d.homeLon)}` : '—' },
        { label: t('距 Home'), value: num(d?.homeDistance, 1, 'm') },
      ],
    },
    {
      title: t('速度与姿态'),
      rows: [
        { label: t('水平速度'), value: num(d?.horizontalSpeed, 1, 'm/s') },
        { label: t('垂直速度'), value: num(d?.verticalSpeed, 1, 'm/s') },
        { label: t('航向（偏航）'), value: num(d?.attitudeHead, 0, '°') },
        { label: t('飞机俯仰'), value: num(d?.attitudePitch, 1, '°') },
        { label: t('飞机横滚'), value: num(d?.attitudeRoll, 1, '°') },
        { label: t('风速'), value: num(d?.windSpeed, 1, 'm/s'), hint: t('由姿态推测，仅供参考') },
        { label: t('风向'), value: d?.windDirection != null ? (WIND_DIRECTIONS[d.windDirection] ?? String(d.windDirection)) : '—' },
      ],
    },
    {
      title: t('云台与相机'),
      rows: [
        { label: t('云台俯仰'), value: num(d?.gimbalPitch, 1, '°') },
        { label: t('云台横滚'), value: num(d?.gimbalRoll, 1, '°') },
        { label: t('云台偏航'), value: num(d?.gimbalYaw, 1, '°') },
        { label: t('变焦倍数'), value: num(d?.zoomFactor, 1, '×') },
        { label: t('存储'), value: n(storage.total) ? `${((n(storage.used) ?? 0) / 1e6).toFixed(1)} / ${((n(storage.total) ?? 0) / 1e6).toFixed(1)} GB` : '—' },
      ],
    },
    {
      title: t('电池'),
      rows: [
        { label: t('总剩余电量'), value: d?.batteryPercent != null ? `${d.batteryPercent} %` : '—' },
        { label: t('剩余飞行时间'), value: duration(d?.remainFlightTime) },
        { label: t('返航所需电量'), value: d?.returnHomePower != null ? `${d.returnHomePower} %` : '—' },
        { label: t('强制降落电量'), value: d?.landingPower != null ? `${d.landingPower} %` : '—' },
        ...batteries.map((b, i) => ({
          label: t('电池 {n}', { n: n(b.index) ?? i }),
          value: `${s(b.capacity_percent)} % · ${num(n(b.voltage) != null ? n(b.voltage)! / 1000 : null, 2, 'V')} · ${num(n(b.temperature), 1, '°C')} · ${t('循环 {n}', { n: s(b.loop_times) })}`,
        })),
      ],
    },
    {
      title: t('定位'),
      rows: [
        { label: t('GPS 卫星数'), value: s(d?.gpsNumber) },
        { label: t('RTK 卫星数'), value: s(d?.rtkNumber) },
        { label: t('收敛状态'), value: [t('未开始'), t('收敛中'), t('收敛成功'), t('收敛失败')][n(pos.is_fixed) ?? -1] ?? '—' },
        { label: t('搜星档位'), value: pos.quality === 10 ? 'RTK fixed' : s(pos.quality) },
      ],
    },
    {
      title: t('限制与安全'),
      rows: [
        { label: t('飞行器限高'), value: num(d?.heightLimit, 0, 'm') },
        { label: t('接近限高'), value: d?.nearHeightLimit == null ? '—' : d.nearHeightLimit ? t('是') : t('否') },
        { label: t('接近限飞区'), value: d?.nearAreaLimit == null ? '—' : d.nearAreaLimit ? t('是') : t('否') },
        { label: t('水平避障'), value: onOff(obstacle.horizon) },
        { label: t('上视避障'), value: onOff(obstacle.upside) },
        { label: t('下视避障'), value: onOff(obstacle.downside) },
      ],
    },
    {
      title: t('遥控器与链路'),
      rows: [
        { label: t('遥控器 SN'), value: s(rc?.sn) },
        { label: t('遥控器电量'), value: rc?.batteryPercent != null ? `${rc.batteryPercent} %` : '—' },
        { label: t('遥控器位置'), value: rc?.lat != null ? `${coord(rc.lat)}, ${coord(rc.lon)}` : '—' },
        { label: t('DRC 链路'), value: [t('未连接'), t('连接中'), t('已连接')][rc?.drcState ?? -1] ?? '—' },
        { label: t('SDR 图传'), value: link.sdr_link_state === 1 ? t('已连接 · 信号 {q}/5', { q: s(link.sdr_quality) }) : link.sdr_link_state === 0 ? t('断开') : '—' },
        { label: t('4G 链路'), value: link['4g_link_state'] === 1 ? t('已连接 · 信号 {q}/5', { q: s(link['4g_quality']) }) : link['4g_link_state'] === 0 ? t('断开') : '—' },
      ],
    },
    {
      title: t('设备信息'),
      rows: [
        { label: t('飞行器 SN'), value: s(d?.sn) },
        { label: t('飞行器固件'), value: s(raw.firmware_version) },
        { label: t('遥控器固件'), value: s(rcRaw.firmware_version) },
        { label: t('累计飞行架次'), value: s(raw.total_flight_sorties) },
        { label: t('累计飞行里程'), value: num(n(raw.total_flight_distance) != null ? n(raw.total_flight_distance)! / 1000 : null, 1, 'km') },
        { label: t('累计飞行时长'), value: num(n(raw.total_flight_time) != null ? n(raw.total_flight_time)! / 3600 : null, 1, 'h') },
        { label: t('激活时间'), value: n(raw.activation_time) ? dateTime(n(raw.activation_time)! * 1000) : '—' },
      ],
    },
  ]
  return groups
}

/** Flattens every raw field (aircraft and RC) for the "all fields" table, so nothing reported is hidden. */
export function flattenRaw(raw: Raw, prefix = ''): InfoRow[] {
  const rows: InfoRow[] = []
  for (const [k, v] of Object.entries(raw)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) rows.push(...flattenRaw(v as Raw, key))
    else if (Array.isArray(v)) {
      if (v.length === 0) rows.push({ label: key, value: '[]' })
      v.forEach((item, i) => {
        if (item && typeof item === 'object') rows.push(...flattenRaw(item as Raw, `${key}[${i}]`))
        else rows.push({ label: `${key}[${i}]`, value: String(item) })
      })
    } else rows.push({ label: key, value: v === null || v === undefined ? '—' : String(v) })
  }
  return rows
}
