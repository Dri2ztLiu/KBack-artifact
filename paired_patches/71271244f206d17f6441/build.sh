#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/kvm/x86.o
