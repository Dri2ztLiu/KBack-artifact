#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/kvm/emulate.o arch/x86/kvm/x86.o arch/x86/kvm/
