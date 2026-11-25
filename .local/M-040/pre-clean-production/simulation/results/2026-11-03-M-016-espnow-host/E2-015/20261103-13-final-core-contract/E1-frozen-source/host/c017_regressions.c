#include "ann.h"
#include <stdio.h>
#include <string.h>

static void setup(ann_node *source, int cached_route) {
    ann_out discard;
    ann_init(source, 1, 100);
    ann_start(source, 0);
    while (ann_next_tx(source, &discard, 0)) {}
    if (cached_route) {
        ann_route *r = &source->routes[0];
        r->used = 1; r->dst = 2; r->path[0] = 1; r->path[1] = 2;
        r->len = 2; r->until = 10000;
    }
}

static ann_packet response(const ann_out *request, unsigned type) {
    ann_packet p = request->packet;
    p.type = (uint8_t)type;
    p.path_len = 2; p.path[0] = 1; p.path[1] = 2;
    p.index = 0; p.ttl = 8; p.payload_len = 0;
    return p;
}

static unsigned expired_events(ann_node *node) {
    ann_event e;
    unsigned count = 0;
    while (ann_next_event(node, &e)) if (e.type == ANN_EXPIRED) count++;
    return count;
}

int main(void) {
    ann_node source, receiver;
    ann_out sent, next;
    ann_packet p, decoded;
    uint8_t wire[250];
    uint32_t seq;
    int len, rc, have, failures = 0;
    unsigned expired;

    /* Deadline=100ms. The adapter processes queued receive events before tick. */
    setup(&source, 1);
    if (ann_submit(&source, 2, ANN_TRANSACTION, 0, "x", 1, 100, 0, 0, &seq)) return 2;
    if (!ann_next_tx(&source, &sent, 0)) return 2;
    p = response(&sent, ANN_ACK);
    len = ann_encode(&p, wire, sizeof(wire));
    rc = ann_receive(&source, 2, wire, (size_t)len, 101);
    ann_tick(&source, 101);
    expired = expired_events(&source);
    printf("{\"case\":\"late_ack\",\"receive_rc\":%d,\"confirmed\":%u,\"expired_events\":%u,\"passed\":%s}\n",
           rc, source.confirmed, expired, !source.confirmed && expired == 1 ? "true" : "false");
    if (source.confirmed || expired != 1) failures++;

    setup(&source, 0);
    if (ann_submit(&source, 2, ANN_TRANSACTION, 0, "x", 1, 100, 0, 0, &seq)) return 2;
    if (!ann_next_tx(&source, &sent, 0)) return 2;
    p = response(&sent, ANN_RREP);
    len = ann_encode(&p, wire, sizeof(wire));
    rc = ann_receive(&source, 2, wire, (size_t)len, 101);
    ann_tick(&source, 101);
    have = ann_next_tx(&source, &next, 101);
    len = have ? ann_encode(&next.packet, wire, sizeof(wire)) : 0;
    printf("{\"case\":\"late_rrep\",\"receive_rc\":%d,\"queued_after_expiry\":%d,\"remaining_ms\":%u,\"self_decode_rc\":%d,\"passed\":%s}\n",
           rc, have, have ? next.packet.remaining_ms : 0,
           have ? ann_decode(&decoded, wire, (size_t)len) : 0, !have ? "true" : "false");
    if (have) failures++;

    setup(&source, 1);
    if (ann_submit(&source, 2, ANN_TRANSACTION, 0, "x", 1, 1000, 0, 0, &seq)) return 2;
    rc = ann_cancel(&source, seq, 0);
    have = ann_next_tx(&source, &next, 0);
    ann_init(&receiver, 2, 200);
    ann_start(&receiver, 0);
    if (have) {
        len = ann_encode(&next.packet, wire, sizeof(wire));
        ann_receive(&receiver, 1, wire, (size_t)len, 0);
    }
    printf("{\"case\":\"cancel_unsent_cached_data\",\"cancel_rc\":%d,\"next_type\":%u,\"receiver_delivered\":%u,\"passed\":%s}\n",
           rc, have ? next.packet.type : 0, receiver.delivered,
           !receiver.delivered && (!have || next.packet.type != ANN_DATA) ? "true" : "false");
    if (receiver.delivered || (have && next.packet.type == ANN_DATA)) failures++;
    return failures ? 1 : 0;
}
