#include "boot_catalog.h"
#include <assert.h>
#include <stdio.h>
int main(void){bc_catalog c;bc_init(&c);uint8_t m[6]={2,0,0,0,0,1};uint32_t b,age;assert(!bc_note(&c,m,11,100));assert(!bc_get(&c,m,200,&b,&age)&&b==11&&age==100);assert(!bc_note(&c,m,22,300));assert(bc_get(&c,m,301,&b,&age)<0);assert(!bc_note(&c,m,22,10000));assert(!bc_get(&c,m,10300,&b,&age)&&b==22);assert(bc_get(&c,m,20000,&b,&age)<0);for(unsigned i=0;i<32;i++){m[5]=(uint8_t)(i+1);assert(!bc_note(&c,m,1,30000));}m[5]=33;assert(bc_note(&c,m,1,30001)<0&&c.full==1);puts("PASS observed source boot freshness, reboot conflict quarantine and 32-entry bound");return 0;}
