#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/core/gen_estimator.o
