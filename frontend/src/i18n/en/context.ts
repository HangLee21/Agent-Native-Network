/**
 * English for words whose meaning depends on where they appear, looked up with tc('<context>', '中文') (docs/i18n.md).
 * phase: a stage on a timeline or phase bar (a noun); state: a status (Taking off, Protected); plural: a heading over a list;
 * verb: a button that does something.
 */
export default {
  'phase::起飞': 'Takeoff',
  'phase::航线': 'Route',
  'phase::飞行': 'Flight',
  'phase::返航': 'RTH',
  'phase::降落': 'Landing',
  'state::起飞': 'Taking off',
  'state::飞行': 'Flying',
  'state::悬停': 'Hovering',
  'state::降落': 'Landing',
  'state::申请控制权': 'Requesting control',
  'state::结束动作': 'Finishing',
  'state::保护': 'Protected',
  'plural::航线': 'Routes',
  'plural::飞机': 'Drones',
  'verb::开启': 'Turn on',
  'deselect::取消': 'Clear',
  // top bar: must fit with two drones and two dogs at 1280 px (the pages keep their full names)
  'tab::记录': 'Logs',
  'tab::演示控制': 'Demo',
  'tab::模拟模式': 'Sim',
  // narrow labels (Watch cards, timeline lanes)
  'short::水平速度': 'Speed',
  'short::垂直速度': 'Climb',
  'short::距起飞点': 'Distance',
} satisfies Record<string, string>
