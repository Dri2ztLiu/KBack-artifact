#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sctp/sm_statefuns.o
