#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/tls/tls_sw.o
