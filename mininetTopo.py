"""
Please add your name: Tan Kai Qun, Jeremy
Please add your matric number: A0136134N
"""

import os
import sys
import atexit
from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.topo import Topo
from mininet.link import Link
from mininet.node import RemoteController


TOPO_INPUT_FILE = "topology.in"

net = None

## Should be run in python3.8
class TreeTopo(Topo):
    def build(self, topo_input_file: str = TOPO_INPUT_FILE):
        with open(file=topo_input_file, mode="r") as f:
            N, M, L = map(int, f.readline().split())

            for i in range(1, N + 1):
                self.addHost(name=f"h{i}")

            for i in range(1, M + 1):
                self.addSwitch(name=f"s{i}")

            for _ in range(L):
                dev1, dev2, bw = map(str.strip, f.readline().split(","))
                self.addLink(node1=dev1, node2=dev2, bw=int(bw))

    # You can write other functions as you need.

    # Add hosts
    # > self.addHost('h%d' % [HOST NUMBER])

    # Add switches
    # > sconfig = {'dpid': "%016x" % [SWITCH NUMBER]}
    # > self.addSwitch('s%d' % [SWITCH NUMBER], **sconfig)

    # Add links
    # > self.addLink([HOST1], [HOST2])


def startNetwork():
    info("** Creating the tree network\n")
    topo = TreeTopo()

    global net
    net = Mininet(
        topo=topo,
        link=Link,
        controller=lambda name: RemoteController(name, ip="SERVER IP"),
        listenPort=6633,
        autoSetMacs=True,
    )

    info("** Starting the network\n")
    net.start()

    # Create QoS Queues
    # > os.system('sudo ovs-vsctl -- set Port [INTERFACE] qos=@newqos \
    #            -- --id=@newqos create QoS type=linux-htb other-config:max-rate=[LINK SPEED] queues=0=@q0,1=@q1,2=@q2 \
    #            -- --id=@q0 create queue other-config:max-rate=[LINK SPEED] other-config:min-rate=[LINK SPEED] \
    #            -- --id=@q1 create queue other-config:min-rate=[X] \
    #            -- --id=@q2 create queue other-config:max-rate=[Y]')

    info("** Running CLI\n")
    CLI(net)


def stopNetwork():
    if net is not None:
        net.stop()
        # Remove QoS and Queues
        os.system("sudo ovs-vsctl --all destroy Qos")
        os.system("sudo ovs-vsctl --all destroy Queue")


if __name__ == "__main__":
    # Force cleanup on exit by registering a cleanup function
    atexit.register(stopNetwork)

    # Tell mininet to print useful information
    setLogLevel("info")
    startNetwork()
