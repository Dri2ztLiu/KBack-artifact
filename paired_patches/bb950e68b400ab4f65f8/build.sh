#!/bin/sh
set -e
make allyesconfig
make -j `nproc` sound/core/seq/seq_queue.o
