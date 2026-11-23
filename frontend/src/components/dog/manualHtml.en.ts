/**
 * English twin of manualHtml.ts (docs/i18n.md): the same table of contents, the same HTML structure and the same ids,
 * so links into the manual (`?id=`, the "?" buttons) work in both languages. ManualContent.vue picks this one when the
 * interface is in English. When the Chinese manual changes, change this file the same way.
 */
export const MANUAL_TOC: { id: string; label: string; sub: boolean }[] = [
  { id: 'm-safety', label: '1. Read first: safety', sub: false },
  { id: 'm-ui', label: '2. Reading the Monitor page', sub: false },
  { id: 'm-results', label: 'How command results are shown', sub: true },
  { id: 'm-drone', label: '3. Drones', sub: false },
  { id: 'm-drone-flow', label: 'Typical workflow', sub: true },
  { id: 'm-drone-prep', label: 'Three things to prepare', sub: true },
  { id: 'm-drone-link', label: 'Connecting the RC to the platform', sub: true },
  { id: 'm-drone-known', label: 'Settled in field tests', sub: true },
  { id: 'm-drone-field', label: 'Still to test', sub: true },
  { id: 'm-s10', label: '4. S10 (Lynx S10)', sub: false },
  { id: 'm-s10-walk', label: 'Standing up and walking', sub: true },
  { id: 'm-s10-map', label: 'Mapping and localization', sub: true },
  { id: 'm-s10-nav', label: 'Navigating to a point', sub: true },
  { id: 'm-s10-arm', label: 'Robot arm', sub: true },
  { id: 'm-s10-grasp', label: 'Visual grasp, one-tap radish grasp', sub: true },
  { id: 'm-lite3', label: '5. Lite3 (Jueying Lite3)', sub: false },
  { id: 'm-lite3-nav', label: 'Outdoor navigation', sub: true },
  { id: 'm-terms', label: '6. Glossary', sub: false },
  { id: 'm-status', label: '7. Common states and errors', sub: false },
  { id: 'm-src', label: '8. Sources', sub: false },
]

const TBD = '<span class="tbd">To confirm with dog team</span>'

export const MANUAL_BODY = `<h1>Guide · Monitor (drones + robot dogs)</h1>
<p class="lead">For first-time users: what to press at each step, why, and what to check when something goes wrong. Terms were checked against DEEP Robotics' official manuals and developer material (section 8); items marked ${TBD} could not be confirmed even after that.</p>

<h2 id="m-safety">1. Read first: safety</h2>
<div class="callout"><b>The emergency stop and soft stop over the network do not replace a physical remote controller.</b> The pilot and the person next to the dog keep a remote controller in hand the whole time.</div>
<ul>
<li><b>Emergency stop (drone), Soft stop (dog)</b>: at the very bottom of the right rail, one per device. They fire only after a <b>0.8 s long press</b>: a progress bar fills the button while you hold it, and letting go early sends nothing. After an emergency stop the drone hovers in place with the propellers still turning (field-tested 11-04; needs "DRC connected"). After a soft stop the S10's joints stop applying force and the dog goes limp; the Lite3 enters its protective state and lies down by itself. Both dogs have to stand up again afterwards.</li>
<li><b>Stop (dog)</b>: sent on a single click; stops what the dog is doing (walking, navigation, the arm and grasping). On the S10, standing up, lying down, changing gait, map operations, taking photos and detection cannot be cancelled midway through the dog team's interface; you have to wait for them to finish. In an emergency, long-press Soft stop. On the Lite3, "Stop" also releases anyone else's control.</li>
<li><b>The platform operates one device at a time</b>: the highlighted tab at the top is the device you are operating. The buttons for each device at the bottom of the right rail can be pressed at any time, and pressing them does not switch devices.</li>
<li><b>Hold to move bypasses obstacle avoidance</b>: the dog goes straight in the direction you press, so watch the video while you drive; the depth image is for viewing only.</li>
<li><b>When the "ago" time turns yellow or grey</b>, the video or data is not live. Do not base decisions on it.</li>
<li><b>Before you start</b>: someone is next to the dog with the physical remote controller in hand; for the Lite3 the official recommendation is at least 75% battery; the video's "ago" time is green. <b>When you are done</b>: S10, stow the arm and lie down; Lite3, lie down and release control.</li>
<li><b>In danger</b>: drone: the pilot takes control back on the remote controller → "Return home" on the platform → long-press "Emergency stop" on the platform. Dog: let go of the direction keys → "Stop" → long-press "Soft stop" → the person next to the dog uses the physical remote controller.</li>
</ul>

<h2 id="m-ui">2. Reading the Monitor page</h2>
<ul>
<li><b>Top tabs</b>: one per device (A and B are drones, S10 and Lite3 are dogs). Green dot: online; grey: "Offline"; red: "Link lost" (it dropped while doing something, which matters); a blinking dot means the platform is making it move right now. Click a tab to operate that device.</li>
<li><b>Main view</b>: the video of the device you are operating. The top-left corner says whose video it is and how long ago it was received.</li>
<li><b>Small tiles, bottom left</b>: the other online devices (map, drone video, dog cameras). Click a tile to show it in the main view; this <b>does not change the device you operate</b>, and the top then says "Operating S10".</li>
<li><b>Top of the right rail</b>: the panel of the device you are operating. A dog's panel starts with the <b>phase bar</b> (which step you are at) and <b>Next step</b> (what to press now, and why some buttons are grey). The buttons are numbered ①②③ in the order you use them.</li>
<li><b>Bottom of the right rail</b>: the safety buttons of every device. Offline devices fold into one line, "Offline: …"; click it to see their last data.</li>
<li><b>Hold to move</b> (when operating a dog, bottom right of the main view): the dog moves only while you hold a direction key. Letting go, or switching to another app or device, stops it at once. Keyboard: W/S forward/back, A/D sideways, Q/E or ←/→ turn (the same as the drone's virtual stick), Space lets go, Esc stops. Space is not a soft stop.</li>
<li>The <button class="qm" tabindex="-1">?</button> next to a term jumps to its explanation in this guide.</li>
</ul>
<h3 id="m-results">How command results are shown</h3>
<table class="t"><tr><th>Shown</th><th>Meaning</th></tr>
<tr><td>Sent, waiting for the dog…</td><td>The command went out; no reply yet.</td></tr>
<tr><td>Accepted by the dog, running N s</td><td>The S10 is doing it; the dog's progress is shown.</td></tr>
<tr><td>Dog reports done / Confirmed</td><td>Finished, and the device says it succeeded.</td></tr>
<tr><td>Dog reports not done: reason</td><td>Finished but did not meet the requirement (for example, the error was too large). <b>"Done" is not the same as "succeeded"</b>.</td></tr>
<tr><td>Received by the dog</td><td>The Lite3 only ever replies "received"; check the video and the state to see whether it actually did it.</td></tr>
<tr><td>Navigation started</td><td>The S10 has started moving on its own; check the navigation status to see whether it arrives.</td></tr>
<tr><td>Failed: reason / Timed out</td><td>Not done, or no reply. The platform never retries by itself; you decide whether to press again.</td></tr>
</table>

<h2 id="m-drone">3. Drones</h2>
<h3 id="m-drone-flow">Typical workflow</h3>
<div class="flowd"><b>Pilot connects</b><i>→</i><b>Request control</b><i>→</i><b>Take off</b><i>→</i><b>Task: Fly to / Orbit / Route / Target</b><i>→</i><b>Return home</b></div>
<ol>
<li>The pilot connects to the platform from "Cloud Service → Open Platform" in Pilot 2 on the remote controller (3.2); the top tab turns green.</li>
<li>Click "Request control" in the right rail and the pilot accepts on the remote controller. From then on the RC's sticks, dials, RTH button and stop button do nothing; the pilot can take control back at any time with "Take control" in Pilot 2.</li>
<li>"Take off": confirm the takeoff height and the RTH altitude.</li>
<li>Pick a task in the task bar; you can press "Stop · Hover" at any time.</li>
<li>"Return home", or the pilot takes control back.</li>
</ol>
<p>For your first time, or before going to the field, read in this order: <b>Preparation (3.1) → Connecting the RC to the platform (3.2) → Settled in field tests (3.3) → Still to test (3.4)</b>. Everything from the former "Field test · Guide for the drone lead" is here, updated with the results of the three field tests on 10-30, 11-04 and 11-05. The grey codes (such as 1-P1, 4-2) match the platform lead's field checklist; just quote the code when you talk it over.</p>

<h3 id="m-drone-prep">3.1 Three things to prepare</h3>
<p><b>① Register as a DJI developer and get 3 credentials</b> <span class="code">1-P1</span></p>
<p>You need an email address, and a credit card or phone number used only to verify your identity (DJI states that nothing is charged). The website is in English; the names in quotes are the buttons on the page.</p>
<ol>
<li>In a computer browser, open https://developer.dji.com/user; it redirects to the "Log in to DJI" page. If you have a DJI account, log in; if not, click "Create Your DJI Account" at the bottom of the page and register.</li>
<li>When the site asks for developer details or to verify a credit card or phone number, follow the prompts.</li>
<li>In the developer center, click "Apps" on the left, then "CREATE APP" on the right.</li>
<li>App Type: "Cloud API"; App Name: "UAV Field Test"; category: whichever is closest; description: "Field test of the drone mission platform"; submit.</li>
<li>Find the app activation email DJI sends you and click the link in it. If it has not arrived, check your spam folder.</li>
<li>Back in the developer center → "Apps" → open the app you just created to see the App ID, App Key and App License. Copy all three in full and send them to the platform lead (the License is long: copy and paste it, do not retype it). If any step is unclear, send the platform lead a screenshot.</li>
</ol>
<p><b>② Prepare the aircraft and the remote controller</b> <span class="code">1-P2</span></p>
<ul>
<li>Fully charge the aircraft batteries and the remote controller.</li>
<li>Bring the propellers, ideally with a spare set.</li>
<li>Photograph the version numbers: aircraft firmware, RC firmware, Pilot 2 version. Don't worry if you can't find them; once connected, the platform can read the aircraft firmware version.</li>
</ul>
<p><b>③ Decide how to get online in the field</b> <span class="code">1-P3</span></p>
<ul>
<li>The remote controller needs internet access in the field: join a Wi-Fi network with internet, or a phone hotspot.</li>
<li>With a phone hotspot, make sure you have enough data: live video uses roughly 0.5–1.5 GB per hour (estimated from DJI's rated video bitrate).</li>
<li>If you can, try it on the remote controller beforehand to make sure it connects to that Wi-Fi or hotspot.</li>
<li>The remote controller does not need to be on the same network as the server or the platform lead's computer.</li>
<li><b>Give each remote controller its own network</b> (its own 4G SIM or its own hotspot): in the 11-04 and 11-05 field tests both went out through the same network, and when it dropped, both went offline together.</li>
</ul>
<p>When all 3 are done, send the platform lead: the App ID, App Key and App License; photos of the version numbers (if you found them); one sentence on which network you will use in the field.</p>

<h3 id="m-drone-link">3.2 Connecting the RC to the platform</h3>
<p>Before you start: the remote controller has internet access. The aircraft can stay off; if it is on, <b>the propellers must be removed</b>.</p>
<div class="callout info"><b>Access page address</b> (enter it in Pilot 2): http://47.93.112.183:8081/pilot/index.html (field server). The port is 8081, not 8080, and the /pilot/index.html part is required.<br><b>Platform access code</b>: ask the platform lead. It has 32 characters: only the digits 0–9 and the lowercase letters a–f.</div>
<p><b>Steps</b> <span class="code">3-P1</span></p>
<ol>
<li>Connect the remote controller to a Wi-Fi network or hotspot with internet access.</li>
<li>Open Pilot 2 and tap "Cloud Service" on the home screen.</li>
<li>Tap "Open Platform" at the bottom right.</li>
<li>Enter the access page address above and tap "Connect" at the top right.</li>
<li>On the access page (in Chinese; its title reads "Drone mission platform · DJI Pilot 2 access"), enter the code in the "Platform access code" box, leave "Remember the access code on this RC" ticked, and tap "Connect to platform".</li>
<li>The page shows the results line by line: ✓ is success, ✗ is failure. Take a photo and send it to the platform lead.</li>
</ol>
<p><b>Remembering the code</b>: once remembered, the access page shows "Access code remembered, connecting automatically…" next time, so you don't have to type it again. If the code has been changed, the page says "The remembered access code is no longer valid; please enter it again". If this remote controller should not remember it, tap "Forget access code".</p>
<p>The page shows, in order: platform login succeeded → License check → RC SN → aircraft SN → set workspace → set platform info → load API module → load device cloud module → load route library module → load live video module → device cloud (MQTT) connected. When the platform has situational awareness on (the other drone shown on the Pilot 2 map), two more lines follow: "Load WS module" and "Load situational awareness module".</p>
<ul>
<li><b>RC SN</b>: a remote controller connecting for the first time shows "First connection" and the platform registers it automatically; the platform can operate it only after the platform lead enables it under "Devices" on the Settings page <span class="code">3-P2</span>. From then on it shows something like "Platform device A, enabled"; if it says "Not enabled yet", contact the platform lead.</li>
<li><b>The License check must be ✓</b>. A ✗ usually means one of the 3 credentials from 3.1 was copied wrongly: copy the App Key again in the developer center and send it to the platform lead (such keys are usually 32 characters; one missing character makes the check fail).</li>
<li><b>Aircraft SN</b>: shown when the aircraft is on; when it is off, the line says "No aircraft connected".</li>
</ul>
<p><b>After connecting</b></p>
<ul>
<li>Press the RC's back button to return to the Pilot 2 home screen, which shows the workspace "UAV field test" (its name is in Chinese).</li>
<li>As long as you don't log out, the remote controller stays online and keeps sending data to the platform.</li>
<li>To disconnect: go back into "Cloud Service → Open Platform" and tap the log-out button at the top right.</li>
<li>After the platform restarts (for example, for an update), log in once more on the access page, or the platform cannot start video.</li>
<li>Try not to re-enter the access page while video is on.</li>
</ul>
<p><b>If connecting fails</b>: photograph the line showing ✗ and send it to the platform lead. Common causes:</p>
<ul>
<li>Wrong address: the port is 8081, not 8080, and the /pilot/index.html part is required.</li>
<li>The remote controller is not connected to the internet.</li>
<li>Wrong access code.</li>
<li>The "device cloud (MQTT)" line: "… disconnected, reconnecting" is normal (Pilot 2 disconnects and reconnects straight away when you re-enter the access page) and turns into "✓ Reconnected" within a few seconds. If it still hasn't connected after 10 s it turns into a red ✗: swipe Pilot 2 away from the recent apps, open it again and go back into the access page; if that doesn't help, restart the remote controller (this happened once on 11-04; reopening Pilot 2 fixed it).</li>
</ul>
<p><b>Route sync check</b> <span class="code">3-★1</span>: after the platform lead clicks "Sync to RC" on the platform, the pilot finds the route in the Pilot 2 route library (the platform lead will tell you its name), downloads and opens it, checks that the number of waypoints, the heights and the waypoint actions match what the platform lead said, and reports back.</p>

<h3 id="m-drone-known">3.3 Settled in field tests</h3>
<p>These conclusions were tested in the field, and the platform is already set up accordingly; the brackets say which field test. From the original checklist, 4-1 control, 4-3 and 5-4 emergency stop, 4-7 RC losing network, 4-8 platform restart, 5-1 one-tap takeoff, 5-2 Fly to, 5-3 RTH, 6-1 point by point and 6-2 update in flight have all been tested; the results are in this table.</p>
<table class="t"><tr><th style="width:110px">What</th><th>Field result</th><th style="width:30%">So we do this</th></tr><tr><td><b>Entering heights</b></td><td>Every height entered on the platform is <b>relative to the takeoff point</b>. For the takeoff target height and Fly to targets, the platform converts to ellipsoid height before sending to the aircraft; the safe takeoff height and the RTH altitude are taken by the aircraft as relative to the takeoff point (10-30, 11-04).</td><td>On the Settings page, set "Check policy for heights with an unclear reference" to <b>Check by inferred reference</b> (the default). With "Dual check", takeoff first overshoots and then comes back down (on 10-30 it climbed to about 59 m before dropping back to 25 m), and the two drones' RTH altitudes cannot be kept apart either.</td></tr><tr><td><b>Laser rangefinder height</b></td><td>The target height from the laser rangefinder is <b>ellipsoid height</b> (10-30: hovering at 20 m and measuring the grass directly below, the laser gave 348.7 m; adding 20 m gives exactly the aircraft's ellipsoid height of 369 m).</td><td>On the Settings page, set "Laser height reference" to <b>ellipsoid height</b> (the default).</td></tr><tr><td><b>Control</b></td><td>After a request, the remote controller shows an authorization prompt; a few seconds after the pilot accepts, the platform shows "In control · DRC". From then on the RC's sticks, dials, RTH button and stop button do nothing.</td><td>Where the authorization prompt and the "Take control" button appear on screen has not been noted yet (4-2).</td></tr><tr><td><b>One-tap takeoff</b></td><td>The aircraft climbs straight up to the height entered and hovers (11-04: entered 20 m, held at 20.0 m). The safe takeoff height is at least 20 m (a DJI rule), so a platform takeoff goes to at least 20 m.</td><td>To go lower, the pilot takes off manually.</td></tr><tr><td><b>Emergency stop</b></td><td>The aircraft stops and hovers in place, <b>propellers still turning</b>; an RTH in progress is interrupted too (11-04: long-pressing Emergency stop at 25 m during RTH, the aircraft hovered at 25 m).</td><td>Emergency stop needs "DRC connected". To carry on after an emergency stop, send a new command (for example, Return home).</td></tr><tr><td><b>RTH</b></td><td>The aircraft reports its own RTH altitude (relative to the takeoff point: the platform sent 20 m, it reported 20 m), which the platform shows in the aircraft info; if the pilot changes it in Pilot 2, the platform sees that too (11-04). When only a few metres from the takeoff point, the aircraft returns at its current height without climbing (10-30).</td><td>Two drones flying at once: RTH altitudes at least 10 m apart, and neither below the highest waypoint of the route being flown (equal is fine).</td></tr><tr><td><b>Obstacle avoidance and trees</b></td><td>The aircraft's own obstacle avoidance keeps working under platform control: near tall trees it climbs by itself (11-04: set to 20 m, it actually rose to 25–29 m during Fly to and RTH). Drone B reported "Obstacle approaching" several times during takeoff and landing, and also briefly flew around obstacles between waypoints (11-05).</td><td>Keep routes and meeting points away from tall trees, or raise everything, leaving about 10 m above the canopy. Take extra care when two drones are kept apart by height: if a tree pushes one up, the height gap shrinks.</td></tr><tr><td><b>Fly to</b></td><td>When the target is lower than the aircraft, it flies level first and descends only near the point. During Fly to the aircraft keeps its camera pointed at the point it is heading for: when it is above the target it slowly tilts down, more the closer it gets; pressing "Down" on the platform meanwhile is turned back by the aircraft within 1–2 s (11-04, 11-05).</td><td>To control the gimbal, wait until it arrives and hovers. Fly at the same height as the target point and the camera won't tilt down.</td></tr><tr><td><b>Routes</b></td><td>With "Point by point", the aircraft reaches the set height at every point and hovers briefly before flying to the next. With "Update in flight", it turns toward the next point as it nears each waypoint without stopping, and may pass a waypoint before reaching the set height (11-04: set to 20 m, it passed waypoint 1 at 22 m). The waypoint option "Hover on arrival and wait for my confirmation" works: it hovers at the point and carries on after you click "Confirm, resume route" (11-05, both drones, 8 waypoints each).</td><td>Use point by point when every point must be at exactly the right height.</td></tr><tr><td><b>Video</b></td><td>Both drones' video can be watched at the same time. The first open retries automatically; if it keeps showing "Connecting video", click "Restart video" on the picture or in the video menu (11-05).</td><td>Try not to have the pilot re-enter the access page while video is on (on 11-05 one drone's stream stopped exactly when the access page was re-entered).</td></tr><tr><td><b>Picking a target with the laser rangefinder</b></td><td>Tap a target on the video to measure it: with the aircraft hovering, 25–50 m all measured fine; while the aircraft is moving it warns "Laser reading unstable" (11-05).</td><td>Hover first, then tap.</td></tr><tr><td><b>Orbit</b></td><td>The platform does not send it when the target is less than 10 m from the aircraft horizontally (as when the target is directly below). On 11-05 the first orbit sent to a real aircraft was rejected by the aircraft (error code 325001); the cause is still being investigated.</td><td>Don't rely on orbit for now.</td></tr><tr><td><b>Fly above target</b></td><td>It gets there; on arrival, the "Look at target" the platform sends automatically is rejected by the aircraft (error code 327019, target directly below), which does not affect the flight (11-05).</td><td>—</td></tr><tr><td><b>Network</b></td><td>When both remote controllers go out through the same network, they drop offline together (once each on 11-04 and 11-05; on 11-05 both reconnected by themselves after a dozen or so seconds). When the network is slow, the position on the platform can lag reality by more than ten seconds (11-04: drone A lagged by 15–20 s).</td><td>Give each its own network. When the network is slow, go by what the pilot sees.</td></tr><tr><td><b>After a platform restart</b></td><td>After the platform restarts (for example, after an update), the remote controller must log in again on the access page before the platform can start video again; otherwise the platform says the RC has not reported a usable live stream (11-05).</td><td>After updating the platform, the platform lead tells the pilots to re-enter the access page.</td></tr></table>

<h3 id="m-drone-field">3.4 Field test: still to test (platform lead and pilot together)</h3>
<div class="callout"><b>Safety rules (for every step)</b>
<ul>
<li>Both stay in voice contact the whole time (radio or phone).</li>
<li>The platform lead says each command out loud before sending it, and sends it only after the pilot says "OK".</li>
<li>When the pilot says "Taking over", the platform lead stops everything at once.</li>
<li>The pilot has the final say on flight safety.</li>
</ul></div>
<p><b>Control: know this beforehand</b></p>
<ul>
<li>When the platform wants to control the aircraft, an authorization prompt appears on the remote controller; the platform gets control only after the pilot accepts.</li>
<li>While the platform has control, the RC's sticks, dials, RTH button and stop button do nothing.</li>
<li>Taking control back: the pilot taps "Take control" in Pilot 2; the platform lead can also click "Release control" in the "…" menu at the top of the right rail to hand control back to the pilot.</li>
<li>In danger, in this order: ① the pilot takes control → ② "Return home" on the platform → ③ long-press "Emergency stop" on the platform (the aircraft hovers in place; needs "DRC connected").</li>
</ul>
<p><b>Before every takeoff, the pilot checks</b>: the site is open, with nobody below or around; you are well away from tall trees, or the flight height leaves margin above the canopy; the battery is well charged (the platform requires at least 25% by default); the RC's network signal is stable; you know where "Take control" is and keep the remote controller in hand throughout.</p>
<p><b>First things on site</b></p>
<ul>
<li>The platform lead spends a few minutes adjusting the network settings (the public address in the field differs from the office's); meanwhile the pilot powers on and checks the aircraft.</li>
<li>The pilot confirms the remote controller is connected to the platform: the Pilot 2 home screen shows the workspace "UAV field test"; if not, connect again as in 3.2.</li>
<li>The platform lead confirms the platform shows "Connected" and the positions of the aircraft and the remote controller.</li>
<li>If the platform has been updated or its database reset, the platform lead checks the Settings page: "Check policy for heights with an unclear reference" is Check by inferred reference, "Laser height reference" is ellipsoid height, both devices are enabled, and the names A / B match the labels on the hardware.</li>
<li>When two drones fly at once, the two pilots cross-check the RTH altitude and RTH mode in Pilot 2 (it should be "Preset altitude"): at least 10 m apart, and neither below the highest waypoint of the route being flown.</li>
</ul>
<h4>On the ground · aircraft on, propellers off</h4>
<table class="t"><tr><th style="width:46px">Code</th><th style="width:130px">Test</th><th>How</th><th style="width:32%">Expect · record</th></tr><tr><td>4-2</td><td><b>Take control</b></td><td>The platform lead clicks "Request control" and the pilot accepts; then the pilot finds "Take control" in Pilot 2 and taps it.</td><td>The platform shows "Control lost" and the RC buttons work normally again. Note where the authorization prompt and the "Take control" button are on screen, and roughly how many seconds pass between the tap and the message on the platform.</td></tr><tr><td>4-4</td><td><b>Aircraft altitude limit</b></td><td>In the "…" menu at the top of the right rail (or the "Pre-flight" card), the platform lead changes "Aircraft altitude limit" to 30 and confirms; the pilot checks the max altitude in Pilot 2.</td><td>The platform shows the setting succeeded; the limit in Pilot 2 changes to 30 m. Note whether it changed.</td></tr><tr><td>4-5</td><td><b>Video latency</b></td><td>With video on, the pilot holds a phone showing a stopwatch in front of the camera.</td><td>The platform lead notes how far the picture lags behind the stopwatch.</td></tr><tr><td>4-6</td><td><b>Command response time</b></td><td>Nothing for the pilot to do; the platform lead looks under "All" in "Recent commands" in the right rail.</td><td>How long each command took from sending to being confirmed by the aircraft.</td></tr><tr><td>4-9</td><td><b>Gimbal speed</b></td><td>In the camera toolbar on the right of the main view, the platform lead sets the speed to "Fast" and holds gimbal "Up" or "Down" for 2 s; then sets "Slow" and holds for 2 s.</td><td>"Fast" turns about 100° in 2 s, "Slow" about 20° (see "Gimbal pitch" in the info panel). Note how far it actually turned.</td></tr></table>
<h4>Low altitude · propellers on, open and empty site, pilot holds the remote controller throughout</h4>
<table class="t"><tr><th style="width:46px">Code</th><th style="width:130px">Test</th><th>How</th><th style="width:32%">Expect · record</th></tr><tr><td>5-5</td><td><b>Emergency landing, forced landing</b></td><td>The pilot takes off manually and hovers low; the platform lead clicks "Request control", the pilot accepts, and once "DRC connected" shows, the platform lead clicks "Land ▾" → "Unlock for 30 s" → "Emergency landing" in the safety area and confirms. Test again: the pilot takes control, takes off manually and hovers; the platform lead requests control the same way and clicks "Forced landing".</td><td>The aircraft lands where it is. Note how each kind of landing behaves and how they differ.</td></tr><tr><td>5-6</td><td><b>Link loss in the air</b> (two runs)</td><td>The platform lead takes off with "Take off", then uses "Fly to" to send the aircraft toward a point. First run: on the way, the platform lead stops the platform on the server; second run: on the way, the pilot turns off the RC's network. The pilot watches and takes control if needed.</td><td>Note what the aircraft did each time (carried on, hovered, returned home…). Restore the platform or the network after each run.</td></tr><tr><td>5-9</td><td><b>RTH from above the RTH altitude</b></td><td>More than 50 m from the takeoff point and higher than the RTH altitude, the platform lead clicks "Return home" and confirms; then try once more within 20 m of the takeoff point.</td><td>Note whether the aircraft returns at its current height or first descends to the RTH altitude, and whether it lands straight away when close.</td></tr></table>
<h4>Routes · 2–3 waypoints, short distance, below the altitude limit</h4>
<table class="t"><tr><th style="width:46px">Code</th><th style="width:130px">Test</th><th>How</th><th style="width:32%">Expect · record</th></tr><tr><td>6-3</td><td><b>Running a route from Pilot 2</b></td><td>The platform lead first clicks "Release control", then "Sync to RC" for this route; the pilot finds it in the Pilot 2 route library, downloads and opens it, checks the number of waypoints, the heights and the waypoint actions, then runs it from Pilot 2.</td><td>The aircraft flies the route and its position shows on the platform map. Note whether Pilot 2 imports and runs it normally, and how it differs from running it from the platform. A waypoint's "wait for my confirmation" has no effect this way.</td></tr></table>
<p><b>To carry on</b>: do the next item only if the previous result was normal; if anything unexpected happens, stop and find out why.</p>
<p><b>When everything is tested</b>: the platform lead clicks "Release control" and the remote controller returns to normal. Together, pass the recorded results to the platform lead, who adds the conclusions to 3.3.</p>

<h2 id="m-s10">4. S10 (DEEP Robotics Lynx S10, with robot arm)</h2>
<p>The S10 is a wheel-legged robot from DEEP Robotics: four legs with a wheel at the end of each. The dog team has fitted it with a six-axis robot arm and a wrist camera, plus their own mapping and navigation software. The S10 does one thing at a time: while an action is running, the dog rejects other actions (except stops), so the other buttons are grey then.</p>
<p>The S10's basic states (official S10 developer material): <b>Idle</b> → <b>Stand</b> → <b>RL control</b> (can walk). From Stand or RL control it can <b>lie down</b>, and after lying down it can stand up again. Entering <b>Damping</b> at any time takes it back to Idle after 3 s, and it then has to stand up again.</p>
<h3 id="m-s10-walk">Standing up and walking (the "Prepare · Walk" tab)</h3>
<div class="flowd"><b>① Stand up</b><i>→</i><b>② Enter RL control</b><i>→</i><b>③ Choose gait (flat / stairs)</b><i>→</i><b>④ Hold to move</b></div>
<ol>
<li><b>Stand up</b>: the dog first stows the arm in its safe position by itself, then stands up.</li>
<li><b>Enter RL control (walking state)</b>: RL control is a walking controller trained with reinforcement learning. The official instruction is "stand first, then enter RL control"; once in it, the joystick (here, the direction keys) sends velocities that make the dog walk. Outside this state the direction keys are grey.</li>
<li><b>Choose a gait</b>: the flat gait is for flat ground, the stairs gait for going up and down steps. ${TBD} how the S10's two gaits differ and which one is the default.</li>
<li><b>Hold to move</b>: the speed is adjustable (straight 0.01–0.15 m/s, turning 0.01–0.30 rad/s; these are limits of the dog team's software). It can't be changed while you hold; a new value takes effect the next time you press after letting go.</li>
</ol>
<p>When you are done: let go; to use the arm, press "Lie down". After a soft stop (damping) the dog goes idle in about 3 s; start again from ① "Stand up". A dog that has just been powered on may also be idle.</p>
<h3 id="m-s10-map">Mapping and localization (the "Mapping" tab)</h3>
<div class="flowd"><b>A① Start mapping</b><i>→</i><b>A② Hold to move around the site</b><i>→</i><b>A③ Save</b><i>……</i><b>B① Load map</b><i>→</i><b>B② Check localization confidence</b><i>→</i><b>B③ Relocalize if not trusted</b></div>
<ul>
<li>Mapping and navigation use software the dog team installed (RTAB-Map for mapping, Nav2 for navigation). The standard S10 has no mapping or navigation of its own (the official product page lists both as S10 Pro features).</li>
<li>New map: start mapping, walk slowly once around the site (switch the left side to "2D map" or "Point cloud" to watch the map grow), give it a name and save it.</li>
<li>Existing map: load it and check the localization confidence; if it isn't trusted, press "Relocalize", or tell the dog roughly where it is now (set the initial pose).</li>
<li>"Clear and rebuild" throws away any unsaved map; you have to tick a confirmation before you can press it.</li>
</ul>
<h3 id="m-s10-nav">Navigating to a point (the "Navigation" tab)</h3>
<div class="flowd"><b>① Localization trusted</b><i>→</i><b>② Arm stowed</b><i>→</i><b>③ Enter target coordinates</b><i>→</i><b>④ Navigate to target</b></div>
<ul>
<li>"Switch to navigation mode" is under "More": it switches the dog's usage mode to navigation (dog team's note: usage mode = 1). Navigation itself does not require switching first; once switched, neither the platform nor the dog team's web page has a button to switch back, so it asks for confirmation before sending. ${TBD} what this mode is for.</li>
<li>Coordinates are positions in the dog's own map (in metres), not latitude and longitude.</li>
<li>"Navigation started" only means the dog has started walking; check the navigation status to see whether it arrives. To stop: "Cancel navigation" or "Stop" at the bottom of the right rail (they do the same; both are rejected while the S10 is doing another long action).</li>
<li>Navigation has no heartbeat: if the platform disconnects, the dog will most likely keep going, and then the only options are a long-press on Soft stop (if commands still get through) or the physical remote controller. During navigation the platform greys out the posture, gait and map buttons; this is the platform's rule, and the dog itself does not block them.</li>
</ul>
<h3 id="m-s10-arm">Robot arm (the "Arm" tab)</h3>
<div class="flowd"><b>Lie down first</b><i>→</i><b>Jog / enter angles / gripper</b><i>→</i><b>Stow to safe position</b><i>→</i><b>Stand up again</b></div>
<ul>
<li>The arm (including "Stow to safe position") moves only when the dog is <b>lying down</b>, or idle, low and still (0–0.15 m off the ground, barely moving), and the joint-angle data must be fresh (within 2 s). When these aren't met, the top of the page says why and offers a "Lie down" button.</li>
<li>Jog: hold a joint's + / − and let go to stop (it relies on a heartbeat like Hold to move: it stops after about 0.6 s without one, and also when you switch to another app or device). Enter angles: fill in the 6 angles and run; a result more than 1° off counts as not done.</li>
<li>The gripper result checks only the opening: when it grips something it stops at a wider opening than the target (for example, target 0 mm, stopped at 46 mm) and shows "Gripper stopped"; that is not a failure.</li>
<li>"Stop arm motion": cancels the rest of the motion and stops where it is. It does not release the gripper and is not a hardware emergency stop.</li>
</ul>
<h3 id="m-s10-grasp">Visual grasp, one-tap radish grasp (the "Grasp" tab)</h3>
<div class="flowd"><b>Lie down</b><i>→</i><b>1 Take photo</b><i>→</i><b>2 Tap the target on the photo</b><i>→</i><b>3 Solve (no motion)</b><i>→</i><b>4 Move to hover position</b><i>→</i><b>Lower, close, lift</b><i>→</i><b>When done: open, stow to safe position, stand up again</b></div>
<ul>
<li>A photo can be solved within 90 s, and a solution executed within 30 s; after that, start over. Don't move the arm between taking the photo and moving to the hover position: if the current joints differ from those at photo time by more than 2°, the dog refuses to execute (the jog buttons are greyed out). ${TBD} whether the dog can stand up directly while holding something (standing up stows the arm automatically).</li>
<li>One-tap radish grasp: detect → move to viewing position → one-tap grasp. It opens the gripper at the start, keeps holding when done, and does not retry by itself on failure. Whether it moves the base: ${TBD}.</li>
</ul>

<h2 id="m-lite3">5. Lite3 (DEEP Robotics Jueying Lite3)</h2>
<div class="flowd"><b>① Take control</b><i>→</i><b>② Stand up</b><i>→</i><b>③ Hold to move</b></div>
<p>Only when needed: "Moving mode" (if the direction keys don't walk the dog) and "Low-speed gait" (to walk slower).</p>
<ol>
<li><b>Take control</b>: only one place can control the Lite3 at a time. Once you take control here, other browser pages and other computers can't move it until you click "Release". Switching to another device or app stops the dog, but you keep control; if the network stalls for 0.5 s the dog stops first, and control is handed back only after 3 s without contact; leaving this page or closing it releases it automatically. Once control is lost it is not taken back automatically; click "Take control" again.</li>
<li><b>Stand up</b>: the maker's stand up / lie down is a single toggle command that alternates between lying and standing; the platform button says what this press will do ("Stand up" while lying, "Lie down" while standing), and is grey while the state hasn't updated or while the dog is standing up. On the first stand-up after power-on, the dog initializes its joints first (about 10 s) and then stands. Press once and watch the state; don't press repeatedly (it can't be pressed again within 3 s).</li>
<li><b>Hold to move</b>: there is only one speed (pressing means full speed in that direction). You can press several keys at once: W+A walks diagonally, W+Q turns while walking.</li>
</ol>
<p><b>Moving mode</b>: according to the official documentation, a standing Lite3 has two modes. In <b>in-place mode</b> the direction keys only tilt the body forward, back, left and right and twist it on the spot, without walking; in <b>moving mode</b> they make it walk forward, back and sideways and turn. In the commands the platform logged on 11-10, the dog walked and turned with the direction keys right after standing up, without "Moving mode" being pressed (also after standing up again after a soft e-stop), so it is no longer a required step. If the direction keys only tilt the body and the dog does not walk, press "Moving mode" once and walk again; pressing it again does no harm.</p>
<p><b>Low-speed gait</b>: a gait for walking slowly on flat ground (officially there are also medium- and high-speed gaits). According to the official documentation the gait can only be changed in moving mode: if the dog does not slow down, press "Moving mode" and then "Low-speed gait".</p>
<p>While it is controlled from another page or computer, you can't control it; if you must stop it, press "Stop", which also releases the other side's control. The dog team's old console has been stopped since 11-10, so their web page can no longer control this dog.</p>
<p>After a soft stop the dog lies down by itself. In the 11-10 test, pressing "Stand up" afterwards stood it up again; if it does not, ask the person next to the dog to use the physical remote controller.</p>
<p>Below 35% battery, charge it soon; <b>below 20% the dog enters low-battery protection and no longer responds to motion commands</b> (official documentation). If the dog has lain down by itself and the battery isn't low, it may be overheat protection: let it cool down before standing it up (the official FAQ suggests about 10 minutes). If it enters loss-of-control protection (it fell over or its legs went out of control), the official procedure is to press STOP so it lies down, then restart the dog; have the person next to the dog do this.</p>
<p><b>Reading the side panel</b> (since 11-11 everything the platform knows about the Lite3 is here): under the next-step line are <b>eight numbers that always stay</b>: battery, motion state, speed, status packet age, GPS satellites, heading, depth ahead (the distance straight ahead seen by the depth camera) and lidar ahead (the nearest obstacle straight ahead seen by the lidar while navigating with avoidance on); they neither scroll nor fold. Below them are groups that fold: click a title to fold or unfold it, and the browser remembers. <b>Prepare · walk</b> (the steps above), <b>Outdoor navigation (GPS)</b>, <b>Motion and attitude</b> (motion state, gait code, attitude, angular rate, body and world velocity, acceleration, motion host position, firmware), <b>Position and heading</b> (fix quality, latitude and longitude, altitude, satellites and HDOP, ground speed, course, heading, antenna, fused position for navigation) and <b>Board and video</b> (board software version, new / old system, who is in control, the board's last error, whether the colour and depth video are streaming, how old each kind of data is). A folded group shows a one-line summary after its title. "Raw reply" in the Details drawer at the bottom is all the raw data the platform has from the new dog system for this dog. Since 11-10 the Lite3 runs on the new dog system, so there is no old-system "SDK", "Control mode", "Image source" or "Stop count".</p>
<h3 id="m-lite3-nav">Outdoor navigation</h3>
<p>Only when the dog reports navigation (installed on the board and switched on in its config). Pick a goal on the map, or draw a route of several points, and the dog walks there by itself.</p>
<ol>
<li><b>Check readiness</b>: the navigation area says which of GPS, heading, localization and lidar is not ready. With dual antennas, draw the route while the board confirms heading at rest. Single-antenna units can align by walking straight ahead.</li>
<li><b>Pick a goal or draw a route</b>: "Pick goal" takes one click; "Draw route" takes successive clicks, and points can be dragged or deleted. The platform checks at once and marks points outside the allowed area, too far from the dog, or too many.</li>
<li><b>Start</b>: take control and stand the dog up first. In the dialog look over the number of points, total length, avoidance, speed level and arrival radius, and tick "The dog is standing".</li>
<li><b>While walking</b>: you can pause, continue, end, change the speed level and switch obstacle avoidance. Pressing a direction key takes over by hand: the dog follows your keys, navigation pauses, and "Continue" walks on after you let go. Stop and Soft stop work at any time and end the navigation.</li>
</ol>
<p><b>When the dog stops by itself</b>: 3 s without the platform it stops and waits; when the network is back it does not walk on by itself, press "Continue"; after 10 s the navigation ends. If your page is silent for 60 s (for example in the background too long) it pauses. Poor GPS, an expired heading alignment or localization not updating pause it. With avoidance on, no lidar data, an obstacle ahead for 20 s or no route found also pause it; then go around the obstacle, switch avoidance off, or take over. Leaving the allowed area, a timeout, or a tilt over 15° end it. Leaving the Monitor page releases control, which ends the navigation. If the page is reloaded or the browser crashes during navigation, the dog walks on; once the old page has been silent for 5 s, press "Take control back" on the new page to carry on.</p>
<p><b>Avoidance off</b>: the dog walks in straight lines, does not go around obstacles and does not stop for them; every other check stays. While it is off the card and the map show "Avoidance off".</p>

<h2 id="m-terms">6. Glossary</h2>
<table class="t"><tr><th style="width:150px">Term</th><th>In plain words</th><th style="width:190px">To ask the dog team</th></tr>
<tr id="g-rl"><td>RL control (walking state, S10)</td><td>A walking controller trained with reinforcement learning. Available only once the dog is standing; once in it, the joystick (the direction keys) sends velocities that make the dog walk. The platform's Hold to move needs the dog in this state.</td><td>How "motion state 17", which the dog team's code checks, maps to the official states</td></tr>
<tr id="g-stand"><td>Stand up / Lie down (S10)</td><td>Makes the dog stand up / lie down. Before standing up, the dog first stows the arm in its safe position by itself. The arm can only be used while the dog is lying down, or idle, low and still.</td><td></td></tr>
<tr id="g-gait"><td>Flat / stairs gait (S10)</td><td>How it walks: the flat gait on flat ground, the stairs gait for going up and down steps.</td><td>${TBD} the exact difference, which is the default, and which one Hold to move needs (the dog team's interface checks the gait)</td></tr>
<tr id="g-damp"><td>Damping (S10 soft stop)</td><td>The joints stop applying force and keep only damping, so the dog goes limp; after 3 s it goes idle and has to stand up again.</td><td>Whether the real dog lies down or sits, and whether it can fall over</td></tr>
<tr id="g-idle"><td>Idle (S10)</td><td>The state right after power-on, or 3 s after a soft stop; the joints apply no force. When idle, the dog can only stand up; when idle, low and still, the arm can also be used.</td><td></td></tr>
<tr id="g-zero"><td>Zeroing (S10)</td><td>Makes the joints find their zero position again (joint initialization). The DEEP Robotics Lite3 manual calls the same kind of operation "return to zero"; it is used when the joints have lost their position and can only be done while lying down.</td><td>${TBD} how it is done on the S10 and what it requires</td></tr>
<tr id="g-navmode"><td>Switch to navigation mode (S10)</td><td>Switches the dog's usage mode to navigation, so that the navigation software the dog team installed drives the dog (dog team's note: usage mode = 1).</td><td>${TBD} what this mode is for; how to switch back (neither the platform nor the dog team's web page has a button to switch back)</td></tr>
<tr id="g-sdk"><td>SDK mode (S10)</td><td>DEEP Robotics' secondary development mode; it can be turned on from the handheld controller only with an authorization code from the manufacturer. This switch is grey on the dog team's web page.</td><td></td></tr>
<tr id="g-toggle"><td>Stand up / Lie down (Lite3)</td><td>One button that alternates between lying down and standing. The first stand-up after power-on initializes the joints first (about 10 s). Don't press it repeatedly; a failure is not resent automatically.</td><td></td></tr>
<tr id="g-moving"><td>Moving mode / in-place mode (Lite3)</td><td>Moving mode: the direction keys make the dog walk and turn. In-place mode: the direction keys only tilt the body forward, back, left and right and twist it on the spot, without walking. lite3-01 walks after standing up without "Moving mode" (field test 11-10); press it only if the direction keys don't walk the dog.</td><td></td></tr>
<tr id="g-low"><td>Low-speed gait (Lite3)</td><td>A gait for walking slowly on flat ground (officially there are also medium- and high-speed gaits). Can only be changed in moving mode. It is not lying down.</td><td></td></tr>
<tr id="g-estop"><td>Soft stop</td><td>S10: enters damping; the joints stop applying force and the dog goes limp. Lite3: lies down by itself; in the 11-10 test, pressing "Stand up" afterwards stood it up again. Neither cuts the power.</td><td></td></tr>
<tr id="g-stop"><td>Stop</td><td>Dog: the S10 stops what it is doing (walking, navigation, the arm; other long actions can't be cancelled midway); the Lite3 stops and releases control (anyone's control). Drone: Stop · Hover.</td><td></td></tr>
<tr id="g-trust"><td>Localization confidence</td><td>Whether the dog is sure where it is on the map. When it isn't trusted, the dog refuses to navigate.</td><td>${TBD} what values it can take; what "withdrawn" means</td></tr>
<tr id="g-mapping"><td>Mapping mode / localization mode</td><td>Mapping: draws a new map while walking. Localization: uses a saved map to work out where the dog is.</td><td></td></tr>
<tr id="g-reloc"><td>Relocalize / initial pose</td><td>Relocalize: makes the dog find itself again in the current map. Initial pose: tells the dog "you are roughly here on the map, facing this way".</td><td>Origin and orientation of the map coordinates</td></tr>
<tr id="g-ik"><td>Inverse kinematics</td><td>Works out how far each of the six joints must turn from "where the end of the arm should go". "Ready" means this calculation can be used now.</td><td></td></tr>
<tr id="g-joint"><td>Joint angles J1–J6</td><td>The angles of the arm's six axes: J1 base rotation, J2 shoulder, J3 elbow, J4 wrist rotation, J5 wrist pitch, J6 gripper rotation.</td><td></td></tr>
<tr id="g-jog"><td>Jog</td><td>Hold to move one joint or the end of the arm slowly; let go to stop.</td><td></td></tr>
<tr id="g-hover"><td>Hover position</td><td>The arm stopped directly above the target (before reaching down to grasp).</td><td></td></tr>
<tr id="g-enable"><td>Enable motors (arm)</td><td>Powers up the arm's motors.</td><td>Whether the board has this function, and when it is needed</td></tr>
<tr id="g-lease"><td>Heartbeat / lease (Hold to move)</td><td>While you hold a direction key, the browser tells the dog "I'm still pressing" every 0.1 s (the heartbeat). The dog keeps moving only for a short time after each heartbeat (S10 0.55 s, arm jog 0.6 s, Lite3 0.5 s) and should stop by itself about that long after the heartbeat stops. This is not a strict guarantee; watch the video. The Lite3's official documentation also says it stops when no joystick command arrives for more than 250 ms.</td><td></td></tr>
<tr id="g-ctl"><td>Control (Lite3)</td><td>Only one place can control the Lite3 at a time. Holding control doesn't move the dog by itself; only holding a direction key does. Stop and Soft stop need no control and anyone can press them, so holding control doesn't keep others from stopping the dog.</td><td></td></tr>
<tr id="g-job"><td>Long action / one thing at a time (S10)</td><td>Most S10 actions take a while to run, and meanwhile the dog accepts no other action (except Soft stop, Stop arm motion and ending a hold); most long actions can't be cancelled midway. "Done" is not the same as "succeeded"; check the result.</td><td></td></tr>
<tr id="g-state"><td>Motion state (Lite3)</td><td>The official states: lying down, ready to stand, standing up, standing (force control, standing or walking), lying down (in progress), loss-of-control protection, posture adjustment, return to zero, AI.</td><td>How the state names the board returns map to these</td></tr>
<tr id="g-battery"><td>Battery</td><td>The battery level the Lite3 reports: below 35%, charge it soon; below 20% the dog no longer responds to motion commands (low-battery protection). The S10 does not report battery. The new system converts both firmware formats to a percentage.</td><td></td></tr>
<tr id="g-fresh"><td>"Ago" time</td><td>How long ago the video or data was received. Green = fresh, yellow = getting old, grey = stale or offline. The S10 is measured by the dog's own clock; the Lite3 by how fresh the board says its data is and when the platform received it.</td><td></td></tr>
<tr id="g-link"><td>Link</td><td>S10: the round trip from the server to the dog and back; above 500 ms the dog may refuse Hold to move. The Lite3's new system talks over MQTT and does not measure this.</td><td></td></tr>
<tr id="g-depth"><td>Depth image</td><td>An image that shows distance by colour. For viewing only; it is not obstacle avoidance.</td><td></td></tr>
<tr id="g-nav-avoid"><td>Obstacle avoidance (Lite3 navigation)</td><td>While navigating, goes around obstacles the lidar sees; slows and then stops when something is close straight ahead; pauses when stopped too long. Can be switched off per dog: then it neither goes around nor stops for obstacles.</td><td></td></tr>
<tr id="g-nav-speed"><td>Speed level (Lite3 navigation)</td><td>How fast navigation walks; you can pick from the levels the dog reports (by default slow 0.12, mid 0.2, fast 0.3 m/s). A dog that reports no levels uses its default speed. Where the dog allows it, a speed can also be typed into the "Custom" box, up to 1.0 m/s. Hold to move is not affected.</td><td></td></tr>
<tr id="g-nav-radius"><td>Arrival radius</td><td>How close to a point counts as arrived, 3 m by default. GPS itself is off by a few metres; too small a radius makes the dog search back and forth near the point.</td><td></td></tr>
<tr id="g-nav-align"><td>Heading alignment</td><td>A single-antenna GPS does not know which way the dog faces. The board takes the dog's IMU yaw and, while the dog walks straight ahead, corrects it to true north with the direction the GPS moved; an alignment holds for 15 minutes.</td><td></td></tr>
<tr id="g-nav-dry"><td>Plan only</td><td>For engineering (New dog system page): the board plans and computes the velocities as usual but does not move the dog.</td><td></td></tr>
<tr id="g-depth-front"><td>Centre depth</td><td>The number at the top left of the Lite3 depth video: the nearest distance in the middle of the depth image (rows 30–70 %, columns 20–80 %), taken as the 2 % quantile of the valid depths there, so a few noisy pixels do not count. In brackets: the share of valid pixels in that area; when it is low (reflections, too close, beyond 10 m) the number is not reliable. When the depth image has not been updated for over 0.5 s only "—" shows. Same method as the old Lite3 card, computed 5 times a second. For viewing only; it is not obstacle avoidance.</td><td></td></tr>
<tr id="g-cloud"><td>Accumulated map point cloud / live lidar</td><td>Accumulated: the 3D points collected during mapping (not updated while the dog stands still). Live: the points the lidar sees at this moment. The two are shown separately.</td><td>Units and coordinate frame</td></tr>
<tr id="g-pilot2"><td>Pilot 2</td><td>The flight app on the remote controller.</td><td></td></tr>
<tr id="g-open"><td>Open Platform / access page</td><td>Open Platform is the entry in Pilot 2's "Cloud Service" for connecting to third-party platforms; open this platform's access page there and enter the access code, and the remote controller is connected to this platform.</td><td></td></tr>
<tr id="g-code"><td>Access code</td><td>The password for this platform, set by the platform lead; it is not issued by DJI.</td><td></td></tr>
<tr id="g-license"><td>App ID / Key / License</td><td>The 3 credentials you get after creating an app on the DJI developer website; Pilot 2 uses them to confirm that DJI allows this platform to connect.</td><td></td></tr>
<tr id="g-sn"><td>SN</td><td>Device serial number.</td><td></td></tr>
<tr id="g-props"><td>Remove propellers</td><td>Take the propellers off. Then even if a takeoff is triggered by mistake, the aircraft can't fly.</td><td></td></tr>
<tr id="g-height"><td>Height above takeoff / ellipsoid height</td><td>Above takeoff: how much higher than the place it took off from; every height entered on the platform is this. Ellipsoid height: height on the earth model GPS uses, which the aircraft uses internally. Near the takeoff point, ellipsoid height = the takeoff point's ellipsoid height + height above takeoff.</td><td></td></tr>
<tr id="g-inferred"><td>Check by inferred reference</td><td>For parameters where DJI's documentation doesn't say which height they use, the platform sends and checks them using the reference it inferred. Field tests have confirmed the inference is right; this is the default on the Settings page.</td><td></td></tr>
<tr id="g-drc"><td>Control / DRC (drone)</td><td>Control: the platform's permission to control the aircraft. It is given only when the pilot accepts on the remote controller, and the pilot can take it back at any time. DRC: the real-time control link between the platform and the aircraft, needed for the emergency stop and the camera.</td><td></td></tr>
</table>

<h2 id="m-status">7. Common states and errors</h2>
<table class="t"><tr><th style="width:230px">You see</th><th>Meaning</th><th style="width:230px">What to do</th></tr>
<tr><td>Failed: another action is running</td><td>The S10 is busy with something else (or the dog team's web page is doing Hold to move)</td><td>Check "Running": if it can be stopped, press "Stop"; if it can't be cancelled, wait for it to finish</td></tr>
<tr><td>Can't be cancelled midway; in an emergency, long-press Soft stop</td><td>The dog team's interface can't cancel actions like standing up, changing gait, map operations, taking photos and detection</td><td>Wait for it to finish (map operations take up to 90 s)</td></tr>
<tr><td>Gripper stopped: at 46 mm (target 0 mm)</td><td>The gripper closed on something and stopped; the result checks only the opening</td><td>Check the video to see whether it is holding the object</td></tr>
<tr><td>Battery 18% (red)</td><td>Lite3 low-battery protection: it doesn't respond to motion commands</td><td>Ask the dog team to change the battery</td></tr>
<tr><td>The Lite3 lay down by itself</td><td>Possibly overheat protection, or a command from elsewhere</td><td>Let it cool down, then stand it up</td></tr>
<tr><td>Failed: arm not stowed / not in RL state</td><td>A precondition isn't met</td><td>Follow the "Next step" hint in the right rail</td></tr>
<tr><td>Dog reports not done: actual error 1.8°</td><td>The arm didn't reach its position (must be within 1°)</td><td>Check the video; run it again if needed</td></tr>
<tr><td>Dog returned without a success flag</td><td>The dog didn't say whether it succeeded</td><td>Check the video and the state</td></tr>
<tr><td>Timed out: no reply from the dog</td><td>Slow network, or the dog is busy</td><td>Check the link and the video; don't press repeatedly</td></tr>
<tr><td>The dog can't find this task</td><td>The dog may have restarted</td><td>Check the dog's current state</td></tr>
<tr><td>Video stopped · last frame N s ago</td><td>The video isn't live</td><td>Don't judge by this picture; check the camera or the network</td></tr>
<tr><td>No new frames</td><td>The Lite3 hasn't received a new image for more than 2 s</td><td>Switch the image source, or check the camera driver</td></tr>
<tr><td>Holding to move, video paused</td><td>The S10 pauses fetching images to keep the heartbeat going</td><td>It resumes when you let go</td></tr>
<tr><td>Reconnecting</td><td>Briefly disconnected (within 5 s)</td><td>Wait a few seconds</td></tr>
<tr><td>Offline</td><td>Can't connect (not powered on, or the network is down)</td><td>Power it on or check the network</td></tr>
<tr><td>Link lost</td><td>Disconnected in the middle of doing something</td><td>Have the person next to the dog, or the pilot, use the physical remote controller</td></tr>
<tr><td>Controlled elsewhere</td><td>The dog team's web page or another computer is controlling the Lite3</td><td>Wait for them to release it; if you must stop it, press "Stop"</td></tr>
<tr><td>Dog service restarted, control disconnected</td><td>The Lite3's access credentials have changed</td><td>"Take control" again; earlier commands are not resent</td></tr>
<tr><td>Stop not confirmed</td><td>The stop sent when you let go got no reply</td><td>Check the video; it should stop by itself after about 0.55 s, and if it doesn't, long-press Soft stop</td></tr>
<tr><td>Link 620 ms, the dog may refuse to move</td><td>Slow network</td><td>Wait for the network to improve before moving</td></tr>
</table>
<h2 id="m-src">8. Sources</h2>
<ul>
<li>Lite3: DEEP Robotics, "Jueying Lite3 Pro User Manual" V2.0.0 (2026-02-27): p. 5 motion modes and gaits, p. 8 the STOP and stand/lie buttons, p. 9 speed levels of the flat gait, p. 12 return to zero, p. 18 "3.5 Return to zero / 3.6 Motion control", p. 21 emergency stop.</li>
<li>Lite3: "Motion host communication interface" (a transcription in the GitHub repository chenzk6/lite3_sdk, corresponding to DEEP Robotics' "Jueying Lite3 Motion Host Communication Interface"): 1.2.2 stand/lie "alternates between the lying state and the initial standing state", 1.2.3 the 250 ms joystick command timeout, 1.2.4 in-place mode and moving mode, 1.2.5 "the gait can be adjusted while in moving mode", 1.3.1 the state table. This is a third-party transcription and may differ from the official original.</li>
<li>S10: the S10 notes in DEEP Robotics' GitHub repository DeepRoboticsLab/sdk_deploy ("stand first, then enter RL control", the controller buttons, an authorization code is needed to turn on SDK mode) and the S10 state machine code (damping returns to idle after 3 s; idle can only go to stand; from stand it goes to RL control or lies down). This is DEEP Robotics' official secondary-development example; the dog team's software may not be exactly the same.</li>
<li>S10: the Lynx S10 product page on the DEEP Robotics website (the standard S10 has no mapping, localization or autonomous navigation; only the S10 Pro does).</li>
<li>Dog team: "Robot dog interface document" (2026-11-06), the interfaces in part one and the special notes in part two; snapshots of the dog team's three web pages (11-05).</li>
</ul>`
