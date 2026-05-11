#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sctp/stream.o net/sctp/stream_sched.o net/sctp/stream_sched_prio.o net/sctp/stream_sched_rr.o include/net/sctp/
