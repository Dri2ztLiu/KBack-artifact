#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/arm/net/bpf_jit_32.o
