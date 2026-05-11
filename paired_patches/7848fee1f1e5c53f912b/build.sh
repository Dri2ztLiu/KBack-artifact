#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/afs/vl_alias.o fs/afs/vlclient.o fs/afs/
