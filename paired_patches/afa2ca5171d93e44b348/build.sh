#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/jbd2/transaction.o
