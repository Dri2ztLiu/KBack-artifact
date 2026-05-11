#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/crypto/aria-aesni-avx-asm_64.o
