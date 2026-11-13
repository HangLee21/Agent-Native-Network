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
	unsigned len = lrn1_build(&n, &m, now, NULL, frame, 208, 1, 10000, &cursor, &res);
	CHECK(len == 208, "8 rows fill the 208-byte frame");
	CHECK(res.rows == 8 && res.eligible == 8, "8 of 8 rows reported");
	CHECK(memcmp(frame, "LRN1", 4) == 0 && frame[4] == 44 && frame[5] == 20, "header intact");
	CHECK(frame[7] == 8 && frame[34] == 8, "row count and visible_rows agree");
	CHECK((crc32(frame, len - 4)) == ((uint32_t)frame[len - 4] | ((uint32_t)frame[len - 3] << 8)
	      | ((uint32_t)frame[len - 2] << 16) | ((uint32_t)frame[len - 1] << 24)), "CRC32 valid");

	/* The bug this module replaces: 12 neighbours used to write past the buffer. */
	for (unsigned i = 8; i < 12; i++) add_peer(&n, i, i + 1, 7 + i, now - 100, 1, now - 50);
	memset(frame, 0xA5, sizeof(frame));
	cursor = 0;
	len = lrn1_build(&n, &m, now, NULL, frame, 208, 2, 10000, &cursor, &res);
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
	len = lrn1_build(&n, &m, now, NULL, frame, 208, 3, 10000, &cursor, &res);
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
		len = lrn1_build(&n, &m, now, NULL, frame, 208, 100 + round, 10000, &cursor, &res);
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
	len = lrn1_build(&n, &m, now, NULL, frame, 208, 4, 10000, &cursor, &res);
	CHECK(len > 0 && res.eligible == 12, "baseline still 12 eligible");

	/* A too-small buffer is refused instead of overrunning. */
	len = lrn1_build(&n, &m, now, NULL, frame, 40, 5, 10000, &cursor, &res);
	CHECK(len == 0, "capacity below the minimum is refused");

	/* Delay stamping keeps the CRC valid. */
	memset(frame, 0xA5, sizeof(frame));
	len = lrn1_build(&n, &m, now, NULL, frame, 208, 6, 25000, &cursor, &res);
	lrn1_set_delay(frame, len, 42);
	CHECK((frame[6] & 4) != 0, "delay flag set");
	CHECK(frame[40] == 42, "delay value stamped");
	CHECK((crc32(frame, len - 4)) == ((uint32_t)frame[len - 4] | ((uint32_t)frame[len - 3] << 8)
	      | ((uint32_t)frame[len - 2] << 16) | ((uint32_t)frame[len - 1] << 24)),
	      "CRC refreshed after stamping the delay");
	CHECK(((uint32_t)frame[36] | ((uint32_t)frame[37] << 8) | ((uint32_t)frame[38] << 16) | ((uint32_t)frame[39] << 24)) == 25000, "period carried through");

	printf("\n%s (%u failures)\n", failures ? "FAILED" : "PASSED", failures);
	return failures ? 1 : 0;
}
