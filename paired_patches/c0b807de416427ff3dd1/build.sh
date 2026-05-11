#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/batman-adv/bat_iv_ogm.o
