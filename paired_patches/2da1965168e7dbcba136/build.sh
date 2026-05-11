#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/infiniband/sw/rxe/rxe_comp.o drivers/infiniband/sw/rxe/rxe_resp.o
