#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/riscv/kernel/asm-offsets.o arch/riscv/kernel/entry.o arch/riscv/include/asm/
