/* Mobility State + geometric link-lifetime prediction. Shadow mode only. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "mobility.h"

#define MM_PER_DEG_LAT 111320000.0
#define LET_CAP_MS 3600000            /* 1 h: beyond this the pair is treated as stable */
#define SIGMA_K 2.0                   /* uncertainty band, standard deviations */

static double clampd(double v, double lo, double hi) { return v < lo ? lo : v > hi ? hi : v; }

static unsigned clampu(unsigned v, unsigned lo, unsigned hi) { return v < lo ? lo : v > hi ? hi : v; }

void mob_init(mob_node* n, uint32_t range_mm) {
	memset(n, 0, sizeof(*n));
	n->range_mm = range_mm ? range_mm : MOB_RANGE_DEFAULT_MM;
	n->degrade_ms = MOB_DEGRADE_MS;
	n->critical_ms = MOB_CRITICAL_MS;
}

void mob_limits(mob_node* n, uint32_t degrade_ms, uint32_t critical_ms) {
	if (degrade_ms > critical_ms) { n->degrade_ms = degrade_ms; n->critical_ms = critical_ms; }
}

static int state_ok(const mob_state* s) {
	if (!(s->valid & 1u)) return 0;
	if (s->lat_e7 < -900000000 || s->lat_e7 > 900000000) return 0;
	if (s->lon_e7 < -1800000000 || s->lon_e7 > 1800000000) return 0;
	if ((s->valid & 2u)) {
		if (s->ve_mm_s < -1000000 || s->ve_mm_s > 1000000) return 0;
		if (s->vn_mm_s < -1000000 || s->vn_mm_s > 1000000) return 0;
		if (s->vu_mm_s < -1000000 || s->vu_mm_s > 1000000) return 0;
	}
	return 1;
}

int mob_self(mob_node* n, const mob_state* s, uint64_t now_ms) {
	(void)now_ms;
	if (!state_ok(s)) { n->rejects++; return -1; }
	n->self = *s;
	n->updates++;
	return 0;
}

static mob_peer* peer_slot(mob_node* n, mid_id peer, int create) {
	mob_peer* free_slot = NULL;
	for (unsigned i = 0; i < MOB_ROWS; i++) {
		if (n->peers[i].used && mid_equal(n->peers[i].peer, peer)) return &n->peers[i];
		if (!n->peers[i].used && !free_slot) free_slot = &n->peers[i];
	}
	if (!create) return NULL;
	if (!free_slot) { n->overflows++; return NULL; }
	memset(free_slot, 0, sizeof(*free_slot));
	free_slot->used = 1;
	free_slot->peer = peer;
	free_slot->risk = MOB_RISK_GOOD;
	free_slot->risk_target = MOB_RISK_GOOD;
	free_slot->let_ms = MOB_LET_INFINITE;
	free_slot->let_low_ms = MOB_LET_INFINITE;
	free_slot->let_high_ms = MOB_LET_INFINITE;
	free_slot->link.ewma_pdr = 1000;
	free_slot->link.etx_x100 = 100;
	return free_slot;
}

int mob_peer_update(mob_node* n, mid_id peer, const mob_state* s, uint64_t now_ms) {
	if (!state_ok(s)) { n->rejects++; return -1; }
	mob_peer* p = peer_slot(n, peer, 1);
	if (!p) return -2;
	/* A sample older than the cached one can never overwrite it: replay and late
	 * delivery are normal on this channel, and regressing the state would flip the
	 * prediction back and forth. */
	if (p->updates && s->sample_ms <= p->remote.sample_ms) { p->stale_rejects++; return -1; }
	p->remote = *s;
	p->received_ms = now_ms;
	p->updates++;
	return 0;
}

int mob_delivery(mob_node* n, mid_id peer, int delivered, int rssi_dbm, uint64_t now_ms) {
	mob_peer* p = peer_slot(n, peer, 1);
	if (!p) return -2;
	uint32_t sample = delivered ? 1000u : 0u;
	uint32_t w = p->link.samples ? p->link.ewma_pdr : sample;
	p->link.ewma_pdr = (w * 7u + sample) / 8u;
	p->link.samples++;
	uint32_t pdr = p->link.ewma_pdr < 20u ? 20u : p->link.ewma_pdr;
	p->link.etx_x100 = clampu(100000u / pdr, 100u, 10000u);
	if (rssi_dbm != 0) p->link.last_rssi = (uint32_t)(int32_t)rssi_dbm;
	if (!p->received_ms) p->received_ms = now_ms;
	return 0;
}

/* Local tangent plane offset in millimetres. Adequate for tens of kilometres. */
static void offset_mm(const mob_state* a, const mob_state* b, double* east, double* north, double* up) {
	double dlat = ((double)b->lat_e7 - (double)a->lat_e7) / 1e7;
	double dlon = ((double)b->lon_e7 - (double)a->lon_e7) / 1e7;
	double lat = ((double)a->lat_e7 + (double)b->lat_e7) / 2e7 * (M_PI / 180.0);
	*north = dlat * MM_PER_DEG_LAT;
	*east = dlon * MM_PER_DEG_LAT * cos(lat);
	*up = (double)b->alt_mm - (double)a->alt_mm;
}

int mob_predict(mob_node* n, mob_peer* p, uint64_t now_ms) {
	if (!p || !p->used) return -1;
	if (!(n->self.valid & 1u) || !(p->remote.valid & 1u)) {
		p->let_ms = p->let_low_ms = p->let_high_ms = MOB_LET_INFINITE;
		p->confidence = 0;
		p->distance_mm = 0;
		p->closing_mm_s = 0;
		return -1;
	}
	double dx, dy, dz;
	offset_mm(&n->self, &p->remote, &dx, &dy, &dz);
	const int have_velocity = (n->self.valid & 2u) && (p->remote.valid & 2u);
	double vx = have_velocity ? (double)p->remote.ve_mm_s - (double)n->self.ve_mm_s : 0.0;
	double vy = have_velocity ? (double)p->remote.vn_mm_s - (double)n->self.vn_mm_s : 0.0;
	double vz = have_velocity ? (double)p->remote.vu_mm_s - (double)n->self.vu_mm_s : 0.0;
	double dist = sqrt(dx * dx + dy * dy + dz * dz);
	double range = (double)n->range_mm;
	p->distance_mm = (uint32_t)clampd(dist, 0.0, 4.0e9);
	double speed = sqrt(vx * vx + vy * vy + vz * vz);
	p->closing_mm_s = dist > 1.0 ? (uint32_t)(int32_t)(-(dx * vx + dy * vy + dz * vz) / dist) : 0;

	int32_t let = MOB_LET_INFINITE;
	if (dist >= range) {
		let = 0;                       /* already outside the modelled reach */
	} else if (!have_velocity || speed < 1.0) {
		let = MOB_LET_INFINITE;        /* no relative motion: nothing to predict */
	} else {
		double a = vx * vx + vy * vy + vz * vz;
		double b = 2.0 * (dx * vx + dy * vy + dz * vz);
		double c = dist * dist - range * range;   /* negative: inside */
		double disc = b * b - 4.0 * a * c;
		if (disc >= 0.0) {
			double t = (-b + sqrt(disc)) / (2.0 * a);   /* exit time */
			if (t > 0.0) {
				double ms = t * 1000.0;
				let = ms >= (double)LET_CAP_MS ? MOB_LET_INFINITE : (int32_t)ms;
			}
		} else {
			let = MOB_LET_INFINITE;    /* closest approach stays inside the range */
		}
	}
	p->let_ms = let;

	/* First-order uncertainty: position error divided by closing speed, plus the
	 * velocity error accumulated over the predicted lifetime. */
	double sigma_r = sqrt((double)n->self.accuracy_mm * n->self.accuracy_mm +
	                      (double)p->remote.accuracy_mm * p->remote.accuracy_mm);
	double sigma_v = sqrt((double)n->self.velocity_accuracy_mm_s * n->self.velocity_accuracy_mm_s +
	                      (double)p->remote.velocity_accuracy_mm_s * p->remote.velocity_accuracy_mm_s);
	if (let == MOB_LET_INFINITE) {
		p->let_low_ms = p->let_high_ms = MOB_LET_INFINITE;
		p->confidence = (!have_velocity || speed < 1.0) ? (p->remote.valid & 1u ? 500u : 0u) : 300u;
	} else {
		double sigma_t = 0.0;
		if (speed > 1.0) sigma_t = sigma_r / speed + ((double)let / 1000.0) * (sigma_v / speed);
		double band = SIGMA_K * sigma_t * 1000.0;
		p->let_low_ms = (int32_t)clampd((double)let - band, 0.0, (double)LET_CAP_MS);
		p->let_high_ms = (int32_t)clampd((double)let + band, 0.0, (double)LET_CAP_MS);
		double rel = band / ((double)let + 1.0);
		p->confidence = clampu((unsigned)(1000.0 * clampd(1.0 - rel, 0.0, 1.0)), 0u, 1000u);
	}

	/* Risk is decided on the conservative bound so an optimistic LET cannot hide a
	 * link that is about to break. Escalation is immediate; relaxation waits for
	 * MOB_HYSTERESIS_MS so a single bad sample cannot flap the state. */
	if (p->confidence < MOB_MIN_CONFIDENCE) {
		/* Inconclusive: keep the last published state instead of starting a transition.
		 * A stable formation has a small relative speed, so the position error alone can
		 * collapse the lower bound to zero; that must not read as "about to break". */
		n->predictions++;
		return 0;
	}
	int32_t headroom = p->let_low_ms;
	uint8_t target = headroom == MOB_LET_INFINITE || (uint32_t)headroom > n->degrade_ms ? MOB_RISK_GOOD
	                 : (uint32_t)headroom > n->critical_ms ? MOB_RISK_DEGRADING
	                 : MOB_RISK_AT_RISK;
	if (target != p->risk) {
		if (!p->risk_since) { p->risk_since = now_ms; p->risk_target = target; }
		int escalate = target > p->risk;
		int persist = now_ms - p->risk_since >= MOB_HYSTERESIS_MS;
		if (escalate || persist) {
			p->risk = target;
			p->risk_since = 0;
			p->risk_target = target;
			n->risk_changes++;
		}
	} else {
		p->risk_since = 0;
		p->risk_target = target;
	}
	n->predictions++;
	return 0;
}

unsigned mob_predict_all(mob_node* n, uint64_t now_ms) {
	unsigned count = 0;
	for (unsigned i = 0; i < MOB_ROWS; i++)
		if (n->peers[i].used) { mob_predict(n, &n->peers[i], now_ms); count++; }
	return count;
}

const char* mob_risk_name(unsigned risk) {
	return risk == MOB_RISK_AT_RISK ? "AT_RISK" : risk == MOB_RISK_DEGRADING ? "DEGRADING" : "GOOD";
}

const char* mob_source_name(unsigned source) {
	switch (source) {
	case MOB_SRC_GNSS: return "gnss";
	case MOB_SRC_INJECTED: return "injected";
	case MOB_SRC_REPLAY: return "replay";
	default: return "unavailable";
	}
}

static int let_finite(int32_t value) { return value == MOB_LET_INFINITE ? 0 : 1; }

int mob_shadow_line(const mob_node* n, const mob_peer* p, uint64_t now_ms, char* out, size_t cap) {
	char peer[18];
	snprintf(peer, sizeof(peer), "%02x:%02x:%02x:%02x:%02x:%02x",
	         p->peer.mac[0], p->peer.mac[1], p->peer.mac[2], p->peer.mac[3], p->peer.mac[4], p->peer.mac[5]);
	unsigned age = now_ms >= p->remote.sample_ms ? (unsigned)(now_ms - p->remote.sample_ms) : 0u;
	int written = snprintf(out, cap,
		"{\"event\":\"mob_shadow\",\"peer\":\"%s\",\"let_ms\":%d,\"let_finite\":%d,"
		"\"let_low_ms\":%d,\"let_high_ms\":%d,\"confidence\":%u,\"risk\":\"%s\","
		"\"distance_mm\":%u,\"closing_mm_s\":%d,\"age_ms\":%u,\"sample_age_ms\":%u,"
		"\"pdr_permille\":%u,\"etx_x100\":%u,\"range_mm\":%u,"
		"\"self_source\":\"%s\",\"peer_source\":\"%s\"}",
		peer,
		let_finite(p->let_ms) ? (int)p->let_ms : -1, let_finite(p->let_ms),
		let_finite(p->let_low_ms) ? (int)p->let_low_ms : -1,
		let_finite(p->let_high_ms) ? (int)p->let_high_ms : -1,
		(unsigned)p->confidence, mob_risk_name(p->risk),
		(unsigned)p->distance_mm, (int)p->closing_mm_s, age, age,
		(unsigned)p->link.ewma_pdr, (unsigned)p->link.etx_x100, (unsigned)n->range_mm,
		mob_source_name(n->self.source), mob_source_name(p->remote.source));
	if (written < 0 || (size_t)written >= cap) return -1;
	return written;
}

int mob_self_line(const mob_node* n, uint64_t now_ms, char* out, size_t cap) {
	unsigned age = now_ms >= n->self.sample_ms ? (unsigned)(now_ms - n->self.sample_ms) : 0u;
	int written = snprintf(out, cap,
		"{\"event\":\"mob_self\",\"valid\":%u,\"fix\":%u,\"source\":\"%s\",\"mode\":%u,"
		"\"lat_e7\":%d,\"lon_e7\":%d,\"alt_mm\":%d,\"ve_mm_s\":%d,\"vn_mm_s\":%d,\"vu_mm_s\":%d,"
		"\"accuracy_mm\":%u,\"velocity_accuracy_mm_s\":%u,\"sample_age_ms\":%u,"
		"\"rows\":%u,\"predictions\":%u}",
		(unsigned)n->self.valid, (unsigned)n->self.fix, mob_source_name(n->self.source),
		(unsigned)n->self.flight_mode,
		(int)n->self.lat_e7, (int)n->self.lon_e7, (int)n->self.alt_mm,
		(int)n->self.ve_mm_s, (int)n->self.vn_mm_s, (int)n->self.vu_mm_s,
		(unsigned)n->self.accuracy_mm, (unsigned)n->self.velocity_accuracy_mm_s, age,
		(unsigned)MOB_ROWS, (unsigned)n->predictions);
	if (written < 0 || (size_t)written >= cap) return -1;
	return written;
}
