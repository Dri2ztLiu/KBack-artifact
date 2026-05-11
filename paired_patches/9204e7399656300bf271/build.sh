#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netfilter/ipset/ip_set_core.o net/netfilter/ipset/ip_set_hash_ip.o net/netfilter/ipset/ip_set_hash_ipmark.o net/netfilter/ipset/ip_set_hash_ipport.o net/netfilter/ipset/ip_set_hash_ipportip.o net/netfilter/ipset/ip_set_hash_ipportnet.o net/netfilter/ipset/ip_set_hash_net.o net/netfilter/ipset/ip_set_hash_netiface.o net/netfilter/ipset/ip_set_hash_netnet.o net/netfilter/ipset/ip_set_hash_netport.o include/linux/netfilter/ipset/
