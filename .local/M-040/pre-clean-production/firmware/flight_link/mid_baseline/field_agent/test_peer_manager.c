#include "peer_manager.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct{uint8_t mac[20][6];int used[20],fail_add,fail_del;unsigned adds,dels;} fake;
static int exists(void*x,const uint8_t*m){fake*f=x;for(unsigned i=0;i<20;i++)if(f->used[i]&&!memcmp(f->mac[i],m,6))return 1;return 0;}
static int add(void*x,const uint8_t*m){fake*f=x;if(f->fail_add){f->fail_add=0;return -1;}for(unsigned i=0;i<20;i++)if(!f->used[i]){f->used[i]=1;memcpy(f->mac[i],m,6);f->adds++;return 0;}return -1;}
static int del(void*x,const uint8_t*m){fake*f=x;if(f->fail_del){f->fail_del=0;return -1;}for(unsigned i=0;i<20;i++)if(f->used[i]&&!memcmp(f->mac[i],m,6)){f->used[i]=0;f->dels++;return 0;}return -1;}
int main(void){fake f={0};pm_state s;pm_init(&s);pm_ops o={exists,add,del,&f};uint8_t b[6]={255,255,255,255,255,255},m[6]={2,0,0,0,0,0};
 for(unsigned i=1;i<=29;i++){m[5]=i;assert(!pm_ensure(&s,&o,m,0));assert(exists(&f,b));}
 assert(f.adds==30&&f.dels==10&&s.evictions==10);unsigned before=f.dels;m[5]=99;assert(pm_ensure(&s,&o,m,1)<0&&f.dels==before);
 f.fail_del=1;assert(pm_ensure(&s,&o,m,0)<0&&exists(&f,b));f.fail_add=1;assert(pm_ensure(&s,&o,m,0)<0&&exists(&f,b));assert(!pm_ensure(&s,&o,m,0));assert(exists(&f,m));
 puts("PASS 20-slot fake driver: broadcast reserved, 29 peers rotate, waiting protected, delete/add failure recovery");return 0;}
