#!/bin/sh
set -e
make allyesconfig
make -j `nproc` sound/core/pcm.o sound/core/pcm_lib.o sound/core/pcm_native.o include/sound/
