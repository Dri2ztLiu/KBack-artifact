#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/riscv/kernel/sbi.o arch/riscv/kernel/sbi_ecall.o arch/riscv/include/asm/ arch/riscv/kernel/
