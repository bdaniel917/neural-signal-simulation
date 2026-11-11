#ifndef V3_DOUBLE_DSP_H
#define V3_DOUBLE_DSP_H
/* Stateful causal double-precision kernels. Coefficients are normalized a0=1. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#define V3_MAX_SOS 24
#define V3_MAX_TAPS 2049

typedef struct { double b0,b1,b2,a0,a1,a2; } V3Section;
typedef struct { int count; V3Section c[V3_MAX_SOS]; } V3Bank;
typedef struct {
    int length; double c[V3_MAX_TAPS];
} V3Taps;
typedef struct { double z1[V3_MAX_SOS],z2[V3_MAX_SOS],peak; } V3SOSState;
typedef struct { const V3Taps *taps; double *history; int next,newest; } V3FIR;
typedef struct { uint64_t multiplies,adds; } V3Ops;
typedef struct {
    double fs,warmup;
    int acquisition_factor,feature_factor;
    V3Taps acquisition,feature;
    V3Bank bandpass,notch;
} V3Config;
typedef struct {
    const V3Config *config;
    V3FIR acquisition,feature;
    V3SOSState bandpass,notch;
    uint64_t input_index,processing_index;
    V3Ops ops;
} V3Pipeline;
typedef struct { int processed,feature_ready; double waveform,raw_power,power; } V3Result;

static double v3_sos(const V3Bank *b,V3SOSState *s,double x,V3Ops *ops) {
    for(int j=0;j<b->count;j++) {
        V3Section c=b->c[j];
        double y=c.b0*x+s->z1[j];
        s->z1[j]=c.b1*x-c.a1*y+s->z2[j];
        s->z2[j]=c.b2*x-c.a2*y;
        s->peak=fmax(s->peak,fmax(fabs(s->z1[j]),fabs(s->z2[j])));
        x=y;
    }
    if(ops){ops->multiplies+=(uint64_t)5*b->count;ops->adds+=(uint64_t)4*b->count;}
    return x;
}
static int v3_read_bank(FILE *f,V3Bank *b) {
    if(fscanf(f,"%d",&b->count)!=1||b->count<0||b->count>V3_MAX_SOS)return 0;
    for(int i=0;i<b->count;i++) {
        V3Section *s=&b->c[i];
        if(fscanf(f,"%lf %lf %lf %lf %lf %lf",&s->b0,&s->b1,&s->b2,&s->a0,&s->a1,&s->a2)!=6)return 0;
        if(!isfinite(s->b0)||!isfinite(s->b1)||!isfinite(s->b2)||s->a0!=1||!isfinite(s->a1)||!isfinite(s->a2))return 0;
    }
    return 1;
}
static int v3_read_taps(FILE *f,V3Taps *t) {
    if(fscanf(f,"%d",&t->length)!=1||t->length<1||t->length>V3_MAX_TAPS)return 0;
    for(int i=0;i<t->length;i++)if(fscanf(f,"%lf",&t->c[i])!=1||!isfinite(t->c[i]))return 0;
    return 1;
}
static int v3_read_config(const char *path,V3Config *c) {
    FILE *f=fopen(path,"r");if(!f)return 0;
    char magic[32];int ok=fscanf(f,"%31s",magic)==1;
    if(ok)ok=magic[0]=='V'&&magic[1]=='3'&&magic[2]=='\0';
    if(ok)ok=fscanf(f,"%lf %d %d %lf",&c->fs,&c->acquisition_factor,&c->feature_factor,&c->warmup)==4;
    if(ok)ok=isfinite(c->fs)&&c->fs>=100&&c->fs<=100000&&c->acquisition_factor>=1&&c->acquisition_factor<=1000&&c->feature_factor>=1&&c->feature_factor<=1000&&isfinite(c->warmup)&&c->warmup>=0;
    if(ok)ok=fabs(c->fs/(c->acquisition_factor*c->feature_factor)-100)<1e-10;
    if(ok)ok=v3_read_taps(f,&c->acquisition)&&v3_read_bank(f,&c->bandpass)&&v3_read_bank(f,&c->notch)&&v3_read_taps(f,&c->feature);
    fclose(f);return ok;
}
static int v3_fir_init(V3FIR *f,const V3Taps *t) {
    f->taps=t;f->next=0;f->newest=0;f->history=calloc((size_t)t->length,sizeof(double));return f->history!=NULL;
}
static void v3_push(V3FIR *f,double x) {
    f->history[f->next]=x;f->newest=f->next;f->next=(f->next+1)%f->taps->length;
}
static double v3_dot(const V3FIR *f,V3Ops *ops) {
    double acc=0;int k=f->newest,n=f->taps->length;
    for(int j=0;j<n;j++){acc+=f->taps->c[j]*f->history[k];k=k? k-1:n-1;}
    if(ops){ops->multiplies+=(uint64_t)n;ops->adds+=(uint64_t)n;}return acc;
}
static int v3_init(V3Pipeline *p,const V3Config *c) {
    *p=(V3Pipeline){0};p->config=c;
    if(!v3_fir_init(&p->acquisition,&c->acquisition))return 0;
    if(!v3_fir_init(&p->feature,&c->feature)){free(p->acquisition.history);return 0;}
    return 1;
}
static void v3_destroy(V3Pipeline *p){free(p->acquisition.history);free(p->feature.history);}
static V3Result v3_step(V3Pipeline *p,double x) {
    const V3Config *c=p->config;V3Result result={0};
    int identity=c->acquisition.length==1&&c->acquisition.c[0]==1;
    if(!identity)v3_push(&p->acquisition,x);
    uint64_t n=p->input_index++;
    if(n%(uint64_t)c->acquisition_factor)return result;
    double v=identity?x:v3_dot(&p->acquisition,&p->ops);
    v=v3_sos(&c->bandpass,&p->bandpass,v,&p->ops);
    v=v3_sos(&c->notch,&p->notch,v,&p->ops);
    result.processed=1;result.waveform=v;
    v3_push(&p->feature,v*v);p->ops.multiplies++;
    uint64_t m=p->processing_index++;
    if(m%(uint64_t)c->feature_factor)return result;
    result.feature_ready=1;result.raw_power=v3_dot(&p->feature,&p->ops);
    result.power=fmax(0,result.raw_power);return result;
}
#endif
