#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/infiniband/sw/rxe/rxe.o drivers/infiniband/sw/rxe/rxe_mcast.o drivers/infiniband/sw/rxe/rxe_net.o drivers/infiniband/sw/rxe/rxe_verbs.o drivers/infiniband/sw/rxe/
