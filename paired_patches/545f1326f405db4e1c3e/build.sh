#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/kvm/lapic.o
