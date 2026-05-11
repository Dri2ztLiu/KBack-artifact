#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/arm64/kernel/mte.o arch/arm64/mm/mteswap.o
