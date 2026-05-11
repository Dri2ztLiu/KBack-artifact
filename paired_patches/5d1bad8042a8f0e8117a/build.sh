#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/x86/crypto/aesni-intel_glue.o
