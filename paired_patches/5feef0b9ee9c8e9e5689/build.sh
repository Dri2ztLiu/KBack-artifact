#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/kvm/svm/svm.o arch/x86/kvm/vmx/vmx.o arch/x86/kvm/x86.o arch/x86/include/asm/
