#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/rose/af_rose.o
