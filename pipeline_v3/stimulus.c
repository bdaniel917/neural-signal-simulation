/* Common-clock analogue approximation and ideal ADC for controlled experiments. */
#include "double_dsp.h"
#include <string.h>
#define PI 3.14159265358979323846
static uint32_t rng;
static double uniform01(void){uint32_t x=rng;x^=x<<13;x^=x>>17;x^=x<<5;rng=x;return ((double)x+.5)/4294967296.;}
static double gaussian(void){double a=uniform01(),b=uniform01();return sqrt(-2*log(a))*cos(2*PI*b);}
int main(int argc,char **argv) {
    if(argc!=3){fprintf(stderr,"stimulus CONFIG OUTPUT.csv\n");return 2;}
    FILE *config=fopen(argv[1],"r");if(!config){perror(argv[1]);return 2;}
    double internal,fs,duration,gain,amp,carrier,modulation,depth,density,line_amp,line_hz,oob_amp,oob_hz;unsigned seed;int mode;
    int n=fscanf(config,"%lf %lf %lf %lf %lf %lf %lf %lf %lf %lf %lf %lf %lf %u %d",&internal,&fs,&duration,&gain,&amp,&carrier,&modulation,&depth,&density,&line_amp,&line_hz,&oob_amp,&oob_hz,&seed,&mode);
    V3Bank bank={0};if(n!=15||!v3_read_bank(config,&bank)){fprintf(stderr,"Invalid source config\n");return 2;}fclose(config);
    double values[]={internal,fs,duration,gain,amp,carrier,modulation,depth,density,line_amp,line_hz,oob_amp,oob_hz};
    for(size_t i=0;i<sizeof(values)/sizeof(values[0]);i++)if(!isfinite(values[i])||values[i]<0){fprintf(stderr,"Source arguments must be finite/nonnegative\n");return 2;}
    if(fs<100||internal<fs||internal>1000000||duration<=0||duration*internal>2e8||gain<=0||carrier<=modulation||depth>1||mode<0||mode>1||fabs(internal/fs-round(internal/fs))>1e-9){fprintf(stderr,"Invalid source bounds\n");return 2;}
    if(fmax(fmax(oob_hz,line_hz),carrier+modulation)>=internal/2){fprintf(stderr,"Source exceeds internal Nyquist\n");return 2;}
    FILE *out=fopen(argv[2],"w");if(!out){perror(argv[2]);return 2;}
    V3SOSState state[4]={{0}};rng=seed?seed:1;
    uint64_t steps=(uint64_t)llround(duration*internal),stride=(uint64_t)llround(internal/fs);
    double sigma=density*sqrt(internal/2),scale=32768.;
    fprintf(out,"t_s,neural_fs,clean_analog_fs,analog_fs,adc_fs,ideal_power_fs2,adc_clip,noise_analog_fs,line_analog_fs,oob_analog_fs\n");
    for(uint64_t i=0;i<steps;i++) {
        double t=(double)i/internal;
        double envelope=mode?(t>=3?amp:0):amp*(1+depth*cos(2*PI*modulation*t));
        double source[4]={envelope*sin(2*PI*carrier*t),density?sigma*gaussian():0,line_amp*sin(2*PI*line_hz*t),oob_amp*sin(2*PI*oob_hz*t)},v[4];
        for(int j=0;j<4;j++)v[j]=v3_sos(&bank,&state[j],gain*source[j],NULL);
        if(i%stride)continue;
        double analog=v[0]+v[1]+v[2]+v[3],raw=round(analog*scale),code=fmax(-scale,fmin(scale-1,raw));
        fprintf(out,"%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g\n",t,source[0],v[0],analog,code/scale,gain*gain*envelope*envelope/2,raw< -scale||raw>scale-1,v[1],v[2],v[3]);
    }
    int failed=ferror(out);if(fclose(out))failed=1;return failed?1:0;
}
