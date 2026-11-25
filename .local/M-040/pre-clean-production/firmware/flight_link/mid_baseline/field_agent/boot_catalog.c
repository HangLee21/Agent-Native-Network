#include "boot_catalog.h"
#include <string.h>
void bc_init(bc_catalog*c){memset(c,0,sizeof(*c));}
int bc_note(bc_catalog*c,const uint8_t mac[6],uint32_t boot,uint64_t now){
 if(!c||!mac||!boot||(mac[0]&1))return -1;
 bc_row*r=0,*free_row=0;for(unsigned i=0;i<BC_ROWS;i++){bc_row*q=&c->rows[i];if(q->used&&!memcmp(q->mac,mac,6)){r=q;break;}if(!free_row&&(!q->used||(now>=q->at&&now-q->at>=BC_FRESH_MS&&now>=q->conflict_until)))free_row=q;}
 if(!r){r=free_row;if(!r){c->full++;return -1;}memset(r,0,sizeof(*r));r->used=1;memcpy(r->mac,mac,6);}
 if(r->boot&&r->boot!=boot&&now>=r->at&&now-r->at<BC_FRESH_MS){r->conflict_until=now+BC_FRESH_MS;c->conflicts++;}
 r->boot=boot;r->at=now;return 0;
}
int bc_get(const bc_catalog*c,const uint8_t mac[6],uint64_t now,uint32_t*boot,uint32_t*age){
 if(!c||!mac||!boot||!age)return -1;
 for(unsigned i=0;i<BC_ROWS;i++){const bc_row*r=&c->rows[i];if(r->used&&!memcmp(r->mac,mac,6)){if(!r->boot||now<r->at||now-r->at>=BC_FRESH_MS||now<r->conflict_until)return -1;*boot=r->boot;*age=(uint32_t)(now-r->at);return 0;}}
 return -1;
}
