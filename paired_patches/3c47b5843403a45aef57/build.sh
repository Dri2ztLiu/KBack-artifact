#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/team/team_core.o
