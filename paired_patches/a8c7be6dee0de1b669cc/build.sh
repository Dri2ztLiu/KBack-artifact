#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/llc/llc_input.o net/llc/llc_s_ac.o net/llc/llc_station.o
