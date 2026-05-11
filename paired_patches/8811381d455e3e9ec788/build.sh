#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/unix/af_unix.o tools/testing/selftests/net/af_unix/msg_oob.o
