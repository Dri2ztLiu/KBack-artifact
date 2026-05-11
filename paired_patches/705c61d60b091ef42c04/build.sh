#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/team/team_core.o drivers/net/team/team_mode_activebackup.o drivers/net/team/team_mode_loadbalance.o include/linux/
