#ifndef E1_NEIGHBOR_SYNC_H
#define E1_NEIGHBOR_SYNC_H
#include "source_route.h"
#include "neighbors.h"
/* Invalidate a formerly confirmed SR peer that ND has evicted. */
void e1_clear_absent_neighbors(sr_node*,nd_node*);
#endif
