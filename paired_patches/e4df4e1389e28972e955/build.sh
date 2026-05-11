#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/8021q/vlan.o net/8021q/vlan_dev.o
