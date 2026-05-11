#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/preload/bpf_preload_kern.o kernel/usermode_driver.o include/linux/
