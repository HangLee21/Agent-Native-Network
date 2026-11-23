/* Host test for the mobility/LET module. No hardware, no network. */
#include <stdio.h>
#include <string.h>
#include "mobility.h"

static unsigned failures;
#define CHECK(cond, msg)                                            \
	do {                                                            \
		if (!(cond)) { printf("FAIL %s\n", msg); failures++; }       \
		else printf("ok   %s\n", msg);                              \
	} while (0)

static mid_id mac(unsigned last) {
	mid_id id = {{0x90, 0xda, 0x72, 0x48, 0xa5, (uint8_t)last}};
	return id;
}

/* One 1e-7 degree of longitude at the equator is 11.132 mm. */
static int32_t lon_e7_for_mm(int64_t mm) { return (int32_t)((double)mm / 11.132); }

static mob_state at(int64_t east_mm, int32_t ve, int32_t alt_mm, uint32_t sample_ms) {
	mob_state s;
	memset(&s, 0, sizeof(s));
	s.valid = 0x7;
	s.fix = MOB_FIX_3D;
	s.source = MOB_SRC_INJECTED;
	s.lat_e7 = 0;
	s.lon_e7 = lon_e7_for_mm(east_mm);
	s.alt_mm = alt_mm;
	s.ve_mm_s = ve;
	s.accuracy_mm = 5000;
	s.velocity_accuracy_mm_s = 500;
	s.sample_ms = sample_ms;
	return s;
}

int main(void) {
	mob_node n;
	mob_init(&n, 120000);
	mob_state self = at(0, 20000, 0, 1000);   /* 20 m/s east */
	CHECK(mob_self(&n, &self, 1000) == 0, "self accepted");

	mid_id peer = mac(0xcc);
	mob_state p = at(100000, 0, 0, 1000);     /* 100 m east, stationary */
	CHECK(mob_peer_update(&n, peer, &p, 1000) == 0, "peer accepted");
	mob_peer* slot = &n.peers[0];
	mob_predict(&n, slot, 1000);
	CHECK(slot->distance_mm > 99500 && slot->distance_mm < 100500, "distance ~100 m");
	CHECK(slot->closing_mm_s > 19500, "closing speed ~20 m/s");
	/* 100 - 20t = -120  ->  t = 11 s */
	CHECK(slot->let_ms > 10800 && slot->let_ms < 11200, "LET ~11.0 s for a receding stationary peer");
	CHECK(slot->let_low_ms <= slot->let_ms && slot->let_ms <= slot->let_high_ms, "band brackets the estimate");

	/* Same velocity on both ends: no relative motion, nothing to predict. */
	mob_state quiet = at(100000, 20000, 0, 2000);
	mob_peer_update(&n, peer, &quiet, 2000);
	mob_predict(&n, slot, 2000);
	CHECK(slot->let_ms == MOB_LET_INFINITE, "co-moving peer has no finite lifetime");

	/* A late sample must not regress the cache. */
	mob_state old = at(50000, 0, 0, 500);
	CHECK(mob_peer_update(&n, peer, &old, 2500) == -1, "older sample rejected");
	CHECK(slot->stale_rejects == 1, "stale reject counted");
	CHECK(slot->remote.sample_ms == 2000, "cache keeps the newer sample");

	/* Risk escalates at once and relaxes only after the hysteresis window.
	 * With R=120 m the shortest lifetime is 2R/|u|, so a realistic 60 m/s closing
	 * speed cannot reach a 3 s critical threshold: it lands in DEGRADING. */
	mob_state hazard = at(118000, -40000, 0, 3000);  /* 60 m/s relative, 2 m inside range */
	mob_peer_update(&n, peer, &hazard, 3000);
	mob_predict(&n, slot, 3000);
	CHECK(slot->risk == MOB_RISK_DEGRADING, "realistic closing speed degrades but is not critical");
	mob_state fast = at(119000, -120000, 0, 3100);   /* 140 m/s separation */
	mob_peer_update(&n, peer, &fast, 3100);
	mob_predict(&n, slot, 3100);
	CHECK(slot->risk == MOB_RISK_AT_RISK, "risk escalates immediately at high separation");

	CHECK(n.risk_changes == 2, "escalation counted (DEGRADING then AT_RISK)");

	mob_state safe = at(20000, 20000, 0, 4000);      /* far and co-moving */
	mob_peer_update(&n, peer, &safe, 4000);
	mob_predict(&n, slot, 4000);
	CHECK(slot->risk == MOB_RISK_AT_RISK, "relaxation waits for hysteresis");
	mob_predict(&n, slot, 4500);
	CHECK(slot->risk == MOB_RISK_AT_RISK, "still waiting at 0.5 s");
	mob_predict(&n, slot, 7000);
	CHECK(slot->risk == MOB_RISK_GOOD, "relaxed after the window");
	CHECK(n.risk_changes == 3, "relaxation counted");

	/* Already outside the modelled range. */
	mob_state outside = at(200000, 0, 0, 8000);
	mob_peer_update(&n, peer, &outside, 8000);
	mob_predict(&n, slot, 8000);
	CHECK(slot->let_ms == 0, "peer outside range has zero lifetime");

	/* Link quality: perfect delivery stays at ETX 1.00, loss degrades it. */
	mid_id other = mac(0x20);
	for (int i = 0; i < 8; i++) mob_delivery(&n, other, 1, -50, 9000 + i);
	mob_peer* q = NULL;
	for (unsigned i = 0; i < MOB_ROWS; i++)
		if (n.peers[i].used && mid_equal(n.peers[i].peer, other)) q = &n.peers[i];
	CHECK(q && q->link.etx_x100 == 100, "clean link has ETX 100");
	for (int i = 0; i < 40; i++) mob_delivery(&n, other, 0, -80, 9100 + i);
	CHECK(q && q->link.etx_x100 >= 500, "loss raises ETX");

	/* Shadow records are single-line JSON objects. */
	char line[512];
	int len = mob_shadow_line(&n, slot, 9500, line, sizeof(line));
	CHECK(len > 0 && line[0] == '{' && line[len - 1] == '}', "shadow line is a JSON object");
	CHECK(strstr(line, "\"event\":\"mob_shadow\"") != NULL, "shadow line names its event");
	CHECK(strstr(line, "\"let_ms\":0") != NULL, "shadow line carries the estimate");
	CHECK(mob_shadow_line(&n, slot, 9500, line, 8) == -1, "short buffer refused");
	CHECK(mob_self_line(&n, 9500, line, sizeof(line)) > 0, "self line renders");

	/* Capacity: the cache is bounded and overflow is counted, not silently dropped. */
	mob_node full;
	mob_init(&full, 120000);
	mob_self(&full, &self, 0);
	for (unsigned i = 0; i < MOB_ROWS + 4; i++) mob_peer_update(&full, mac(i), &p, 1000 + i);
	CHECK(full.overflows == 4, "cache overflow counted");

	printf("\n%s (%u failures)\n", failures ? "FAILED" : "PASSED", failures);
	return failures ? 1 : 0;
}
