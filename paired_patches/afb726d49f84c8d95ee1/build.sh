#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/riscv/mm/pageattr.o
