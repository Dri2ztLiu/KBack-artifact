#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/rcu/srcutree.o
