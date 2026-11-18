/* Host test for the LRN1 frame builder: capacity, truncation and row fairness. */
#include <stdio.h>
#include <string.h>
#include "lrn1_frame.h"

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

static uint32_t crc32(const uint8_t* p, unsigned n) {
	uint32_t crc = 0xffffffffu;
	while (n--) {
		crc ^= *p++;
		for (unsigned i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
	}
	return ~crc;
}

static void add_peer(nd_node* n, unsigned slot, unsigned last, uint32_t boot, uint64_t seen,
                     int confirmed, uint64_t ack) {
	n->peers[slot].used = 1;
	n->peers[slot].id = mac(last);
	n->peers[slot].boot = boot;
	n->peers[slot].seen = seen;
	n->peers[slot].confirmed = confirmed;
	n->peers[slot].ack = ack;
}

int main(void) {
	nd_node n;
	mt_node m;
	memset(&n, 0, sizeof(n));
	memset(&m, 0, sizeof(m));
	n.self = mac(0xf8);
	n.boot = 1234;
	n.group = 31;
	const uint64_t now = 100000;

	/* Eight neighbours fit exactly in 208 bytes. */
	for (unsigned i = 0; i < 8; i++) add_peer(&n, i, i + 1, 7 + i, now - 100, 1, now - 50);
	uint8_t frame[232];
	memset(frame, 0xA5, sizeof(frame));            /* canary beyond the 208-byte capacity */
	lrn1_result res;
	uint32_t cursor = 0;
	unsigned len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 208, 1, 10000, &cursor, &res);
	CHECK(len == 208, "8 rows fill the 208-byte frame");
	CHECK(res.rows == 8 && res.eligible == 8, "8 of 8 rows reported");
	CHECK(memcmp(frame, "LRN1", 4) == 0 && frame[4] == 44 && frame[5] == 20, "header intact");
	CHECK(frame[7] == 8 && frame[34] == 8, "row count and visible_rows agree");
	CHECK(frame[35] == 7, "node number 7 rides in header byte 35");
CHECK((crc32(frame, len - 4)) == ((uint32_t)frame[len - 4] | ((uint32_t)frame[len - 3] << 8)
	      | ((uint32_t)frame[len - 2] << 16) | ((uint32_t)frame[len - 1] << 24)), "CRC32 valid");

	/* The bug this module replaces: 12 neighbours used to write past the buffer. */
	for (unsigned i = 8; i < 12; i++) add_peer(&n, i, i + 1, 7 + i, now - 100, 1, now - 50);
	memset(frame, 0xA5, sizeof(frame));
	cursor = 0;
	len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 208, 2, 10000, &cursor, &res);
	CHECK(len == 208, "12 neighbours still produce a 208-byte frame");
	CHECK(res.rows == 8 && res.eligible == 12, "truncated to 8 of 12");
	CHECK(frame[7] == 8, "frame reports 8 rows, not 12");
	CHECK(frame[34] == 12, "visible_rows tells the gateway that 4 were dropped");
	unsigned canary_ok = 1;
	for (unsigned i = 208; i < sizeof(frame); i++) if (frame[i] != 0xA5) canary_ok = 0;
	CHECK(canary_ok, "nothing written past the 208-byte capacity");

	/* Non-bidirectional neighbours go first: they carry the topology change. */
	n.peers[10].ack = now - 10000;                  /* ack beyond 9 s -> heard, not bidirectional */
	n.peers[11].ack = now - 10000;
	cursor = 0;
	len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 208, 3, 10000, &cursor, &res);
	int saw_sick = 0;
	for (unsigned r = 0; r < frame[7]; r++) {
		const uint8_t* row = frame + 44 + 20 * r;
		if (row[10] != 2) saw_sick = 1;
	}
	CHECK(saw_sick, "a non-bidirectional row is always included");

	/* Round-robin: across successive frames every neighbour is reported at least once. */
	cursor = 0;
	int seen[32];
	memset(seen, 0, sizeof(seen));
	for (unsigned round = 0; round < 6; round++) {
		len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 208, 100 + round, 10000, &cursor, &res);
		for (unsigned r = 0; r < frame[7]; r++) {
			const uint8_t* row = frame + 44 + 20 * r;
			for (unsigned i = 0; i < 12; i++)
				if (!memcmp(row, n.peers[i].id.mac, 6)) seen[i] = 1;
		}
	}
	int all = 1;
	for (unsigned i = 0; i < 12; i++) if (!seen[i]) all = 0;
	CHECK(all, "every neighbour appears within a few frames (round-robin)");

	/* Filtering is honoured. */
	for (unsigned i = 0; i < 12; i++) n.peers[i].seen = now - 100;
	len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 208, 4, 10000, &cursor, &res);
	CHECK(len > 0 && res.eligible == 12, "baseline still 12 eligible");

	/* A too-small buffer is refused instead of overrunning. */
	len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 40, 5, 10000, &cursor, &res);
	CHECK(len == 0, "capacity below the minimum is refused");

	/* Delay stamping keeps the CRC valid. */
	memset(frame, 0xA5, sizeof(frame));
	len = lrn1_build(&n, &m, now, NULL, 7, NULL, NULL, frame, 208, 6, 25000, &cursor, &res);
	lrn1_set_delay(frame, len, 42);
	CHECK((frame[6] & 4) != 0, "delay flag set");
	CHECK(frame[40] == 42, "delay value stamped");
	CHECK((crc32(frame, len - 4)) == ((uint32_t)frame[len - 4] | ((uint32_t)frame[len - 3] << 8)
	      | ((uint32_t)frame[len - 2] << 16) | ((uint32_t)frame[len - 1] << 24)),
	      "CRC refreshed after stamping the delay");
	CHECK(((uint32_t)frame[36] | ((uint32_t)frame[37] << 8) | ((uint32_t)frame[38] << 16) | ((uint32_t)frame[39] << 24)) == 25000, "period carried through");

	/* Optional status block: present only when the caller passes it, and it costs rows. */
	lrn1_status st;
	memset(&st, 0, sizeof(st));
	st.reset_reason = LRN1_RST_BROWNOUT;
	st.supply_mv = 4875;
	st.die_temp_c = 41;
	st.heap_free_kb = 123;
	st.queue_depth = 3;
	st.tx_drops = 2;
	st.routes = 4;
	st.lora_tx_power_dbm = 14;
	st.lora_sf = 7;
	st.fault_flags = LRN1_FAULT_UNDERVOLTAGE;
	st.pi_flags = LRN1_PI_ALIVE | LRN1_PI_NETWORK;
	st.pi_cpu_temp_c = 52;
	st.pi_load_x10 = 23;
	st.pi_mem_free_mb = 1024;
	st.pi_wifi_rssi = -61;
	st.serial_errors = 1;
	st.battery_pct = 88;

	cursor = 0;
	len = lrn1_build(&n, &m, now, NULL, 7, &st, NULL, frame, 208, 7, 10000, &cursor, &res);
	CHECK((frame[6] & LRN1_FLAG_STATUS) != 0, "status flag set");
	CHECK((frame[6] & LRN1_FLAG_GPS) == 0, "gps flag clear when not passed");
	CHECK(len == 44 + 20 * res.rows + 24 + 4, "status block accounted in the length");
	CHECK(res.rows == 6, "status block drops the row capacity from 8 to 6");
	{
		const uint8_t* b = frame + 44 + 20 * res.rows;
		CHECK(b[0] == LRN1_RST_BROWNOUT, "reset reason round-trips");
		CHECK((b[1] | (b[2] << 8)) == 4875, "supply millivolts round-trip");
		CHECK((int8_t)b[3] == 41 && b[4] == 123, "die temp and heap round-trip");
		CHECK((b[10] & LRN1_FAULT_UNDERVOLTAGE) != 0, "fault flags round-trip");
		CHECK(b[11] == (LRN1_PI_ALIVE | LRN1_PI_NETWORK), "pi flags round-trip");
		CHECK((b[14] | (b[15] << 8)) == 1024, "pi free memory round-trips");
		CHECK(b[18] == 88, "battery percent round-trips");
	}
	CHECK((crc32(frame, len - 4)) == ((uint32_t)frame[len - 4] | ((uint32_t)frame[len - 3] << 8)
	      | ((uint32_t)frame[len - 2] << 16) | ((uint32_t)frame[len - 1] << 24)),
	      "CRC valid with a status block");

	/* Reserved GPS block: encoded, flagged, and decoded back. */
	lrn1_gps g;
	memset(&g, 0, sizeof(g));
	g.flags = LRN1_GPS_VALID | LRN1_GPS_FIX_3D;
	g.lat_e7 = 40003456;          /* 4.0003456 deg */
	g.lon_e7 = -116307890;        /* -11.6307890 deg */
	g.alt_m = 512;
	g.speed_cms = 1500;
	g.heading_cdeg = 27645;
	g.sats = 11;
	g.hdop_x10 = 8;
	g.vdop_x10 = 12;

	cursor = 0;
	len = lrn1_build(&n, &m, now, NULL, 7, &st, &g, frame, 208, 8, 10000, &cursor, &res);
	CHECK((frame[6] & LRN1_FLAG_STATUS) && (frame[6] & LRN1_FLAG_GPS), "both block flags set");
	CHECK(len == 44 + 20 * res.rows + 24 + 20 + 4, "gps block accounted in the length");
	CHECK(res.rows == 5, "both blocks still allow 5 rows at 208 bytes");
	{
		const uint8_t* b = frame + 44 + 20 * res.rows + 24;
		int32_t lat = (int32_t)((uint32_t)b[1] | ((uint32_t)b[2] << 8) | ((uint32_t)b[3] << 16) | ((uint32_t)b[4] << 24));
		int32_t lon = (int32_t)((uint32_t)b[5] | ((uint32_t)b[6] << 8) | ((uint32_t)b[7] << 16) | ((uint32_t)b[8] << 24));
		CHECK(lat == 40003456, "latitude round-trips as signed 1e-7 degrees");
		CHECK(lon == -116307890, "longitude round-trips as signed 1e-7 degrees");
		CHECK((b[9] | (b[10] << 8)) == 512, "altitude round-trips");
		CHECK((b[13] | (b[14] << 8)) == 27645, "heading round-trips");
		CHECK(b[15] == 11 && b[16] == 8 && b[17] == 12, "sats and dop round-trip");
	}
	CHECK((crc32(frame, len - 4)) == ((uint32_t)frame[len - 4] | ((uint32_t)frame[len - 3] << 8)
	      | ((uint32_t)frame[len - 2] << 16) | ((uint32_t)frame[len - 1] << 24)),
	      "CRC valid with both blocks");

	/* Capacity helper must agree with what the builder actually produced. */
	CHECK(lrn1_capacity(208, 0, 0) == 8, "capacity without blocks is 8");
	CHECK(lrn1_capacity(208, 1, 0) == 6, "capacity with status is 6");
	CHECK(lrn1_capacity(208, 1, 1) == 5, "capacity with both is 5");
	CHECK(lrn1_capacity(112, 1, 1) == 1, "small buffers still fit one row");

	printf("\n%s (%u failures)\n", failures ? "FAILED" : "PASSED", failures);
	return failures ? 1 : 0;
}
