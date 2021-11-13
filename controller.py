'''
Please add your name: Tan Kai Qun, Jeremy
Please add your matric number: A0136134N
'''

from struct import pack
import sys
import os
import time
from collections import defaultdict
from sets import Set

from pox.core import core

import pox.openflow.libopenflow_01 as of
import pox.openflow.discovery
import pox.openflow.spanning_forest

from pox.lib.revent import *
from pox.lib.util import dpid_to_str
from pox.lib.addresses import IPAddr, EthAddr

log = core.getLogger()

TTL = 30  ## in seconds
NORMAL_TRAFFIC = 0
PREMIUM_TRAFFIC = 1
FIREWALL_PRIORITY = 200
TRANSFER_PRIORITY = 100


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

    def _handle_PacketIn(self, event):
        # install entries to the route table
        def install_enqueue(event, packet, out_port, q_id):
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet=packet, in_port=in_port)
            msg.data = event.ofp
            msg.hard_timeout = TTL
            ## msg.actions.append(of.ofp_action_enqueue(port=out_port, queue_id=q_id))
            msg.actions.append(of.ofp_action_enqueue(port=out_port))
            msg.priority = TRANSFER_PRIORITY

            event.connection.send(msg)

        def forward(message=None):
            message and log.debug(message)

            self.forward_table.learn_entry(dpid=dpid, mac=src_mac, port=in_port)

            out_port = self.forward_table.get_port(dpid=dpid, mac=dst_mac)

            if dst_mac.is_multicast or out_port is None:
                flood()
                return
            
            ## TODO: implement different queue
            q_id = NORMAL_TRAFFIC
            
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

        forward()

    def _handle_ConnectionUp(self, event):
        dpid = dpid_to_str(event.dpid)
        log.debug("Switch %s has come up.", dpid)

        # Send the firewall policies to the switch
        def sendFirewallPolicy(connection, policy):
            # define your message here

            # OFPP_NONE: outputting to nowhere
            # msg.actions.append(of.ofp_action_output(port = of.OFPP_NONE))
            pass

        # for i in [FIREWALL POLICIES]:
        #     sendFirewallPolicy(event.connection, i)


def launch():
    # Run discovery and spanning tree modules
    pox.openflow.discovery.launch()
    pox.openflow.spanning_forest.launch()

    # Starting the controller module
    core.registerNew(Controller)
