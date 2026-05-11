#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/rds/rdma.o net/rds/send.o
