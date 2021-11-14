"""
Please add your name: Tan Kai Qun, Jeremy
Please add your matric number: A0136134N
"""

import os
import time
from collections import defaultdict

from pox.core import core

import pox.openflow.libopenflow_01 as of
import pox.openflow.discovery
import pox.openflow.spanning_forest

from pox.lib.revent import *
from pox.lib.packet import ipv4, ethernet
from pox.lib.util import dpid_to_str
from pox.lib.addresses import IPAddr, EthAddr

log = core.getLogger()
dirname, _ = os.path.split(os.path.abspath(__file__))

TTL = 30  ## in seconds
NORMAL_TRAFFIC = 0
PREMIUM_TRAFFIC = 1
FIREWALL_PRIORITY = 200
FORWARD_PRIORITY = 100
POLICY_INPUT_FILE = os.path.join(dirname, "policy.in")


class ForwardTableEntry:
    def __init__(self, port, ttl=TTL):
        self.port = port
        self.ttl = ttl
        self.created_at = time.time()

    def has_expired(self):
        return time.time() > self.created_at + self.ttl


class ForwardTable:
    def __init__(self):
        ## shape: {dpid: {mac: entry}}
        self.table = defaultdict(dict)

    def validate_entry(self, dpid, mac):
        """Check if entry has expired and delete it"""
        if mac not in self.table[dpid] or not self.table[dpid][mac].has_expired():
            return

        del self.table[dpid][mac]

    def learn_entry(self, dpid, mac, port):
        self.validate_entry(dpid=dpid, mac=mac)

        if mac in self.table[dpid]:
            return

        self.table[dpid][mac] = ForwardTableEntry(port=port)

    def get_port(self, dpid, mac):
        self.validate_entry(dpid=dpid, mac=mac)

        entry = self.table[dpid].get(mac)

        if entry is None:
            return

        return entry.port


class Controller(EventMixin):
    def __init__(self):
        self.listenTo(core.openflow)
        core.openflow_discovery.addListeners(self)

        self.forward_table = ForwardTable()
        self.firewall_policies = set()
        self.premium_traffic_hosts = set()

        self.load_policies()

    def load_policies(self, policy_file=POLICY_INPUT_FILE):
        with open(policy_file, mode="r") as f:
            N, M = map(int, f.readline().split())

            for _ in range(N):
                policy = tuple(map(str.strip, f.readline().split(",")))

                if len(policy) < 3:
                    policy = (None,) + policy

                self.firewall_policies.add(policy)

            for _ in range(M):
                host = f.readline().strip()
                self.premium_traffic_hosts.add(IPAddr(host))

    def _handle_PacketIn(self, event):
        # install entries to the route table
        def install_enqueue(event, packet, out_port, q_id):
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet=packet, in_port=in_port)
            msg.data = event.ofp
            msg.hard_timeout = TTL
            msg.actions.append(of.ofp_action_enqueue(port=out_port, queue_id=q_id))
            msg.priority = FORWARD_PRIORITY

            event.connection.send(msg)

        def get_dst_ip():
            if packet.type == ethernet.ARP_TYPE:
                return packet.payload.protodst

            if packet.type == ethernet.IP_TYPE:
                return packet.payload.dstip

            return None

        def forward(message=None):
            message and log.debug(message)

            self.forward_table.learn_entry(dpid=dpid, mac=src_mac, port=in_port)

            out_port = self.forward_table.get_port(dpid=dpid, mac=dst_mac)

            if dst_mac.is_multicast or out_port is None:
                flood(
                    message="Flooding: src_mac: %s | in_port: %i" % (src_mac, in_port)
                )
                return

            q_id = (
                PREMIUM_TRAFFIC
                if get_dst_ip() in self.premium_traffic_hosts
                else NORMAL_TRAFFIC
            )

            install_enqueue(event=event, packet=packet, out_port=out_port, q_id=q_id)

        # When it knows nothing about the destination, flood but don't install the rule
        def flood(message=None):
            """Flood the packet (extracted from l2_learning.py example)"""
            message and log.debug(message)

            msg = of.ofp_packet_out()
            msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
            msg.data = event.ofp
            msg.in_port = in_port

            event.connection.send(msg)

        packet, in_port, dpid = event.parsed, event.port, event.dpid
        src_mac, dst_mac = packet.src, packet.dst

        forward(
            message="Forward: dpid: %i | src_mac: %s | in_port: %i | dst_mac: %s"
            % (dpid, src_mac, in_port, dst_mac)
        )

    def _handle_ConnectionUp(self, event):
        dpid = dpid_to_str(event.dpid)
        log.debug("Switch %s has come up.", dpid)

        # Send the firewall policies to the switch
        def send_firewall_policy(connection, policy):
            src_ip, dst_ip, dst_port = policy

            msg = of.ofp_flow_mod()
            msg.priority = FIREWALL_PRIORITY
            msg.match.dl_type = ethernet.IP_TYPE
            msg.match.nw_proto = ipv4.TCP_PROTOCOL
            msg.match.nw_dst = IPAddr(addr=dst_ip)
            msg.match.tp_dst = int(dst_port)
            if src_ip is not None:
                msg.match.nw_src = IPAddr(addr=src_ip)

            connection.send(msg)

        for policy in self.firewall_policies:
            send_firewall_policy(connection=event.connection, policy=policy)


def launch():
    # Run discovery and spanning tree modules
    pox.openflow.discovery.launch()
    pox.openflow.spanning_forest.launch()

    # Starting the controller module
    core.registerNew(Controller)
