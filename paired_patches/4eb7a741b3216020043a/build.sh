#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/safesetid/securityfs.o
