#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/net/bpf_jit_comp.o kernel/bpf/core.o include/linux/
