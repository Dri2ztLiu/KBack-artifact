#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/vmw_vsock/af_vsock.o net/vmw_vsock/vsock_bpf.o include/net/
