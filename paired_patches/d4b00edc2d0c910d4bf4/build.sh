#!/bin/sh
set -e
make allyesconfig
make -j `nproc` arch/arm/vfp/entry.o arch/arm/vfp/vfphw.o
