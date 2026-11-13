/* Host check for the local re-discovery change in source_route.c failed().
 * Not part of the repository test suite; built ad hoc against the real sources. */
#include <stdio.h>
#include <string.h>
#include "source_route.h"

static int failures;
static void check(const char *name, int ok) {
    if (ok) printf("ok   %s\n", name);
    else { printf("FAIL %s\n", name); failures++; }
}
static mid_id mk(int last) {
    mid_id a = {{0x90, 0xda, 0x72, 0x48, 0xa4, (uint8_t)last}};
    return a;
}

int main(void) {
    sr_node n;
    sr_out out;
    int got, r;
    const uint64_t t0 = 1000;
    mid_id self = mk(0xf8), A = mk(0x01), B = mk(0x02), dst = mk(0x20);
    uint8_t payload[4] = {1, 2, 3, 4};

    /* --- 1. unchanged behaviour: no route starts one RREQ, packet stays pending --- */
    sr_init(&n, self, 7, 31);
    sr_neighbor(&n, A, 1, 1);
    sr_neighbor(&n, B, 2, 1);
    r = sr_submit(&n, dst, 11, payload, 4, t0);
    check("submit without a route is accepted and starts a round", r == 0);
    got = sr_next_tx(&n, &out, t0);
    check("first queued frame is an RREQ", got == 1 && sr_base_type(out.packet.type) == SR_RREQ);
    check("RREQ broadcast to the group", out.next.mac[0] == 255 && out.next.mac[5] == 255);

    /* --- 2. a local DATA dying on its own first edge is re-discovered once --- */
    memset(&n, 0, sizeof(n));
    sr_init(&n, self, 7, 31);
    sr_neighbor(&n, A, 1, 1);
    sr_neighbor(&n, B, 2, 1);
    n.now = t0;
    n.routes[0] = (sr_route){.used = 1, .dst = dst,
                             .path = {.n = 3, .path = {self, A, B}},
                             .request = 5, .first_boot = 1, .until = t0 + 10000};
    r = sr_submit(&n, dst, 21, payload, 4, t0);
    check("submit uses the installed cached route", r == 0);
    got = sr_next_tx(&n, &out, t0);
    check("queued frame is DATA on hop 1", got == 1 && sr_base_type(out.packet.type) == SR_DATA && out.packet.index == 1);
    check("DATA next hop is the route first hop", mid_equal(out.next, A));

    unsigned before = n.retries;
    sr_tx_result(&n, &out, 0, t0 + 10);
    check("first-edge failure triggers exactly one re-discovery", n.retries == before + 1);
    got = sr_next_tx(&n, &out, t0 + 20);
    check("re-discovery emits a new RREQ", got == 1 && sr_base_type(out.packet.type) == SR_RREQ);
    check("old route was invalidated by the failure",
          !(n.routes[0].used && n.routes[0].request == 5 && n.routes[0].until == t0 + 10000));

    /* --- 3. the retry budget is one per packet identity --- */
    memset(n.rounds, 0, sizeof(n.rounds));
    n.routes[0] = (sr_route){.used = 1, .dst = dst,
                             .path = {.n = 3, .path = {self, A, B}},
                             .request = 6, .first_boot = 1, .until = t0 + 10000};
    r = sr_submit(&n, dst, 21, payload, 4, t0 + 30);
    check("same seq can be submitted again for the budget test", r == 0);
    got = sr_next_tx(&n, &out, t0 + 31);
    check("DATA queued again", got == 1 && sr_base_type(out.packet.type) == SR_DATA);
    before = n.retries;
    sr_tx_result(&n, &out, 0, t0 + 40);
    check("second failure of the same seq does not retry again", n.retries == before);

    /* --- 4. a different seq still gets its own single retry --- */
    memset(n.rounds, 0, sizeof(n.rounds));
    n.routes[0] = (sr_route){.used = 1, .dst = dst,
                             .path = {.n = 3, .path = {self, A, B}},
                             .request = 7, .first_boot = 1, .until = t0 + 10000};
    r = sr_submit(&n, dst, 22, payload, 4, t0 + 50);
    check("new seq accepted", r == 0);
    got = sr_next_tx(&n, &out, t0 + 51);
    check("DATA queued for the new seq", got == 1 && sr_base_type(out.packet.type) == SR_DATA);
    before = n.retries;
    sr_tx_result(&n, &out, 0, t0 + 60);
    check("new seq gets its own retry", n.retries == before + 1);

    printf("\n%s (%d failure%s)\n", failures ? "FAILED" : "PASSED", failures, failures == 1 ? "" : "s");
    return failures ? 1 : 0;
}
