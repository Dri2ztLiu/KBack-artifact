#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/security.o security/selinux/hooks.o
