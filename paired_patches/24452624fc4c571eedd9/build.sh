#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/vmw_vsock/virtio_transport_common.o
