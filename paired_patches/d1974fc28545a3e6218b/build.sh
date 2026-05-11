#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/arm64/mm/copypage.o
