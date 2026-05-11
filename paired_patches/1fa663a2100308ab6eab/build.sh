#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/bpf/lpm_trie.o
