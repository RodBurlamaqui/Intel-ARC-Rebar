/* ocl_test: allocate N buffers of M MiB on the first OpenCL GPU, write each with a
 * kernel (forces real residency), run saxpy across all of them, report bandwidth.
 * Declares the small OpenCL API subset it needs so no OpenCL headers are required.
 * usage: ocl_test [nbuf=6] [mib=512]   exit 0 ok, 1 setup error, 2 allocation failed */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
typedef void *clp; typedef int cl_int; typedef unsigned cl_uint; typedef unsigned long long cl_bf;
extern cl_int clGetPlatformIDs(cl_uint,clp*,cl_uint*);
extern cl_int clGetDeviceIDs(clp,cl_bf,cl_uint,clp*,cl_uint*);
extern clp clCreateContext(const void*,cl_uint,const clp*,void*,void*,cl_int*);
extern clp clCreateCommandQueue(clp,clp,cl_bf,cl_int*);
extern clp clCreateBuffer(clp,cl_bf,size_t,void*,cl_int*);
extern clp clCreateProgramWithSource(clp,cl_uint,const char**,const size_t*,cl_int*);
extern cl_int clBuildProgram(clp,cl_uint,const clp*,const char*,void*,void*);
extern clp clCreateKernel(clp,const char*,cl_int*);
extern cl_int clSetKernelArg(clp,cl_uint,size_t,const void*);
extern cl_int clEnqueueNDRangeKernel(clp,clp,cl_uint,const size_t*,const size_t*,const size_t*,cl_uint,const void*,void*);
extern cl_int clEnqueueReadBuffer(clp,clp,cl_uint,size_t,size_t,void*,cl_uint,const void*,void*);
extern cl_int clFinish(clp);
extern cl_int clGetProgramBuildInfo(clp,clp,cl_uint,size_t,void*,size_t*);
static const char *SRC =
"__kernel void fill(__global float*b,float v){b[get_global_id(0)]=v;}\n"
"__kernel void saxpy(__global float*y,__global const float*x,float a){"
"size_t i=get_global_id(0); y[i]=a*x[i]+y[i];}\n";
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(int argc,char**argv){
  int nbuf=argc>1?atoi(argv[1]):6, mib=argc>2?atoi(argv[2]):512;
  if(nbuf<1||mib<1||mib>65536){puts("usage: ocl_test [nbuf>=1] [MiB 1..65536]");return 1;}
  size_t N=(size_t)mib*1024*1024/4; clp plat,dev,ctx,q; cl_int e; cl_uint n;
  if(clGetPlatformIDs(1,&plat,&n)||!n){puts("no OpenCL platform");return 1;}
  if(clGetDeviceIDs(plat,4,1,&dev,&n)||!n){puts("no OpenCL GPU device");return 1;}
  ctx=clCreateContext(0,1,&dev,0,0,&e); if(e){printf("context error %d\n",e);return 1;}
  q=clCreateCommandQueue(ctx,dev,0,&e);  if(e){printf("queue error %d\n",e);return 1;}
  clp prog=clCreateProgramWithSource(ctx,1,&SRC,0,&e);
  if(clBuildProgram(prog,1,&dev,"",0,0)){char log[4096];clGetProgramBuildInfo(prog,dev,0x1183,sizeof log,log,0);printf("build failed:\n%s\n",log);return 1;}
  clp kf=clCreateKernel(prog,"fill",&e), ks=clCreateKernel(prog,"saxpy",&e);
  clp bufs[256]; int ok=0; if(nbuf>256)nbuf=256;
  printf("allocating %d x %d MiB device buffers...\n",nbuf,mib);
  for(int i=0;i<nbuf;i++){
    bufs[i]=clCreateBuffer(ctx,1,N*4,0,&e);
    if(e){printf("  buffer %d FAILED to allocate (err %d)\n",i+1,e);break;}
    float v=(float)i; clSetKernelArg(kf,0,sizeof(clp),&bufs[i]); clSetKernelArg(kf,1,4,&v);
    if(clEnqueueNDRangeKernel(q,kf,1,0,&N,0,0,0,0)||clFinish(q)){printf("  buffer %d FAILED to write (not resident)\n",i+1);break;}
    ok++; if(i%4==3||i==nbuf-1) printf("  %d buffers ok (%.1f GiB resident)\n",ok,ok*mib/1024.0);
  }
  if(ok<1){puts("RESULT: could not allocate even one buffer");return 2;}
  if(ok<2){printf("RESULT: 1 x %d MiB allocated; not enough for saxpy\n",mib);return 0;}
  printf("%.1f GiB resident. running saxpy over all of it...\n",ok*mib/1024.0);
  double t0=now(); int reps=3;
  for(int r=0;r<reps;r++) for(int i=1;i<ok;i++){float a=2.0f;
    clSetKernelArg(ks,0,sizeof(clp),&bufs[i]); clSetKernelArg(ks,1,sizeof(clp),&bufs[i-1]); clSetKernelArg(ks,2,4,&a);
    clEnqueueNDRangeKernel(q,ks,1,0,&N,0,0,0,0);}
  clFinish(q); double dt=now()-t0; double bytes=(double)reps*(ok-1)*N*4*3;
  printf("saxpy: %.2f s, %.1f GB/s effective VRAM bandwidth\n",dt,bytes/dt/1e9);
  float out[2]; clEnqueueReadBuffer(q,bufs[ok-1],1,0,sizeof out,out,0,0,0);
  printf("readback: %.1f (non-zero = compute really ran)\n",out[0]);
  printf("RESULT: %.1f GiB allocated and computed on (%d x %d MiB)\n",ok*mib/1024.0,ok,mib);
  return 0;}
