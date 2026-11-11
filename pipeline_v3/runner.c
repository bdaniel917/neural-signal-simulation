/* Streaming double pipeline. Input/outputs are trace CSVs, not a device interface. */
#include "double_dsp.h"
#include <string.h>
#include <errno.h>
#include <limits.h>
typedef struct { double t,neural,clean,analog,adc,ideal,clip,noise,line,oob; } Row;
static int read_row(FILE *f,Row *r) {
    char line[4096];if(!fgets(line,sizeof(line),f))return ferror(f)?-1:0;
    int n=sscanf(line,"%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf",&r->t,&r->neural,&r->clean,&r->analog,&r->adc,&r->ideal,&r->clip,&r->noise,&r->line,&r->oob);
    if(n!=10||!isfinite(r->t)||!isfinite(r->adc)||!isfinite(r->clean)||!isfinite(r->ideal)||(r->clip!=0&&r->clip!=1))return -1;
    return 1;
}
int main(int argc,char **argv) {
    if(argc<5||argc>7){fprintf(stderr,"runner CONFIG INPUT.csv FEATURES.csv BLOCK_SIZE [WAVEFORM.csv|-] [DENSE_POWER.csv]\n");return 2;}
    char *end;errno=0;long block=strtol(argv[4],&end,10);
    if(errno||*end||block<1||block>65536){fprintf(stderr,"Invalid block size\n");return 2;}
    V3Config *cfg=calloc(1,sizeof(*cfg));if(!cfg||!v3_read_config(argv[1],cfg)){fprintf(stderr,"Invalid configuration\n");free(cfg);return 2;}
    V3Pipeline noisy={0},clean={0};
    if(!v3_init(&noisy,cfg)||!v3_init(&clean,cfg)){fprintf(stderr,"Allocation failed\n");return 2;}
    Row *rows=calloc((size_t)block,sizeof(*rows));
    FILE *input=fopen(argv[2],"r"),*output=fopen(argv[3],"w"),*wave=argc>=6&&strcmp(argv[5],"-")?fopen(argv[5],"w"):NULL;
    FILE *dense=argc==7?fopen(argv[6],"w"):NULL;
    if(!rows||!input||!output||(argc>=6&&strcmp(argv[5],"-")&&!wave)||(argc==7&&!dense)){perror("Open/allocation");return 2;}
    char header[4096];if(!fgets(header,sizeof(header),input)){fprintf(stderr,"Missing CSV header\n");return 2;}
    fprintf(output,"t_s,available_no_compute_s,raw_power_fs2,power_fs2,clean_raw_power_fs2,clean_power_fs2,ideal_power_fs2,flags,clamped,clean_clamped\n");
    if(wave)fprintf(wave,"t_s,filtered_fs,clean_filtered_fs\n");
    if(dense)fprintf(dense,"t_s,raw_power_fs2,power_fs2,clean_raw_power_fs2,clean_power_fs2\n");
    double last_clip=-1e30;uint64_t count=0,clips=0;int failed=0;
    for(;;) {
        size_t n=0;int status=0;
        while(n<(size_t)block&&(status=read_row(input,&rows[n]))==1)n++;
        if(status<0){fprintf(stderr,"Invalid input row\n");failed=1;break;}
        if(!n)break;
        double available=rows[n-1].t;
        for(size_t i=0;i<n;i++,count++) {
            Row r=rows[i];
            if(fabs(r.t-(double)count/cfg->fs)>1e-9){fprintf(stderr,"Input timestamp/phase discontinuity\n");failed=1;break;}
            if(r.clip){last_clip=r.t;clips++;}
            V3Result y=v3_step(&noisy,r.adc),ref=v3_step(&clean,r.clean);
            if(!isfinite(y.waveform)||!isfinite(y.raw_power)||!isfinite(ref.raw_power)){fprintf(stderr,"Nonfinite DSP output\n");failed=1;break;}
            if(wave&&y.processed)fprintf(wave,"%.17g,%.17g,%.17g\n",r.t,y.waveform,ref.waveform);
            /* Diagnostic only: read FIR history without updating state or deployed counters. */
            if(dense&&y.processed) {
                double p=v3_dot(&noisy.feature,NULL),q=v3_dot(&clean.feature,NULL);
                if(!isfinite(p)||!isfinite(q)){fprintf(stderr,"Nonfinite dense diagnostic\n");failed=1;break;}
                fprintf(dense,"%.17g,%.17g,%.17g,%.17g,%.17g\n",r.t,p,fmax(0,p),q,fmax(0,q));
            }
            if(y.feature_ready) {
                int flags=(r.t<cfg->warmup?1:0)|(r.t-last_clip<=cfg->warmup?2:0)|(y.raw_power<0?4:0);
                fprintf(output,"%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d,%d,%d\n",r.t,available,y.raw_power,y.power,ref.raw_power,ref.power,r.ideal,flags,y.raw_power<0,ref.raw_power<0);
            }
        }
        if(failed)break;
    }
    fprintf(stderr,"{\"input_samples\":%llu,\"processing_samples\":%llu,\"adc_clips\":%llu,\"multiplications\":%llu,\"additions\":%llu,\"bandpass_state_peak\":%.17g,\"notch_state_peak\":%.17g}\n",
        (unsigned long long)count,(unsigned long long)noisy.processing_index,(unsigned long long)clips,
        (unsigned long long)noisy.ops.multiplies,(unsigned long long)noisy.ops.adds,noisy.bandpass.peak,noisy.notch.peak);
    if(dense){failed|=ferror(dense);if(fclose(dense))failed=1;}
    failed|=ferror(output);if(wave){failed|=ferror(wave);if(fclose(wave))failed=1;}
    if(fclose(output))failed=1;
    fclose(input);free(rows);v3_destroy(&noisy);v3_destroy(&clean);free(cfg);return failed?1:0;
}
