#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/infiniband/sw/rxe/rxe_qp.o
