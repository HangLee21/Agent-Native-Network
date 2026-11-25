#include "deployment.h"
#include <string.h>

int mid_deployment_validate(const mid_deployment *p, mid_id self) {
    uint8_t encoded[MID_DEPLOYMENT_BYTES];
    int own = 0;
    size_t len = 0;
    while (len < sizeof(p->profile_id) && p->profile_id[len]) {
        unsigned char c = (unsigned char)p->profile_id[len++];
        if (c < 32 || c > 126) return -1;
    }
    if (!len || len > 64 || p->autostart > 1 ||
        mid_table_encode(&p->table, encoded, sizeof(encoded)) < 0) return -1;
    const mid_table *t = &p->table;
    for (unsigned i = 0; i < t->n; i++) if (mid_equal(t->nodes[i], self)) own = 1;
    if (!own) return -1;
    for (unsigned f = 0; f < t->k; f++) {
        int next[MID_N];
        for (unsigned i = 0; i < t->n; i++) {
            next[i] = -1;
            for (unsigned j = 0; j < t->n; j++) if (t->w[f][i][j]) {
                if (t->w[f][i][j] != 65535 || next[i] >= 0) return -1;
                next[i] = (int)j;
            }
        }
        if (next[t->src[f]] < 0) return -1;
        for (unsigned i = 0; i < t->n; i++) if (next[i] >= 0) {
            unsigned visited = 0;
            int at = (int)i;
            while (at != t->dst[f]) {
                if (at < 0 || (visited & (1u << (unsigned)at))) return -1;
                visited |= 1u << (unsigned)at;
                at = next[at];
            }
        }
    }
    return 0;
}

int mid_deployment_encode(const mid_deployment *p, mid_id self, uint8_t *out, size_t cap) {
    if (mid_deployment_validate(p, self)) return -1;
    size_t name = strlen(p->profile_id);
    uint8_t table[MID_DEPLOYMENT_BYTES];
    int n = mid_table_encode(&p->table, table, sizeof(table));
    if (n < 0 || cap < 10 + name + (size_t)n) return -1;
    memcpy(out, "MDEP", 4);
    out[4] = 1; out[5] = p->autostart; out[6] = (uint8_t)name; out[7] = 0;
    out[8] = (uint8_t)n; out[9] = (uint8_t)((unsigned)n >> 8);
    memcpy(out + 10, p->profile_id, name);
    memcpy(out + 10 + name, table, (size_t)n);
    return (int)(10 + name + (size_t)n);
}

int mid_deployment_decode(mid_deployment *p, mid_id self, const uint8_t *in, size_t len) {
    mid_deployment tmp = {0};
    if (len < 10 || len > MID_DEPLOYMENT_BYTES || memcmp(in, "MDEP", 4) ||
        in[4] != 1 || in[5] > 1 || !in[6] || in[6] > 64 || in[7]) return -1;
    unsigned n = in[8] | ((unsigned)in[9] << 8);
    if (len != 10u + in[6] + n) return -1;
    tmp.autostart = in[5];
    for (unsigned i = 0; i < in[6]; i++) if (in[10+i] < 32 || in[10+i] > 126) return -1;
    memcpy(tmp.profile_id, in + 10, in[6]);
    if (mid_table_decode(&tmp.table, in + 10 + in[6], n) || mid_deployment_validate(&tmp, self)) return -1;
    *p = tmp;
    return 0;
}

int mid_deployment_install(mid_node *node, const mid_deployment *p, mid_id self, uint64_t now) {
    if (mid_deployment_validate(p, self)) return -1;
    mid_init(node, self, self, 0);
    node->table = p->table;
    node->have_table = 1;
    const uint16_t draw[MID_F] = {0};
    return mid_tick(node, now, draw) == 1 ? 0 : -1;
}
