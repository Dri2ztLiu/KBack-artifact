#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/virtio/virtio_ring.o
