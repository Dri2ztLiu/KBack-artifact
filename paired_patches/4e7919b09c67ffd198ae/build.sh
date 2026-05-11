#!/bin/sh
set -e
make allyesconfig
make -j `nproc` sound/core/control_led.o
