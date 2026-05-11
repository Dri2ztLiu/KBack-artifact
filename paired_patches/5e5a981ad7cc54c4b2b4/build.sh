#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/llc/af_llc.o net/llc/llc_s_ac.o include/net/
