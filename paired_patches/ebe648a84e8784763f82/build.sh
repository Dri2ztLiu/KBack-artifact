#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/bpf_lru_list.o kernel/bpf/
