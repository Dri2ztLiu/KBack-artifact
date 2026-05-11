#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/char/hw_random/virtio-rng.o
