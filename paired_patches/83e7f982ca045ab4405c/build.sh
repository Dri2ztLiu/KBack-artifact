#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/entry/vsyscall/vsyscall_64.o arch/x86/mm/fault.o arch/x86/include/asm/
