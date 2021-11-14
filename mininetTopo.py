"""
Please add your name: Tan Kai Qun, Jeremy
Please add your matric number: A0136134N
"""

import os
import atexit

from typing import Optional

from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.topo import Topo
from mininet.link import Link, Intf
from mininet.node import RemoteController, OVSKernelSwitch

dirname, _ = os.path.split(os.path.abspath(__file__))

TOPO_INPUT_FILE = os.path.join(dirname, "topology.in")
CONTROLLER_IP = "0.0.0.0"
CONTROLLER_PORT = 6633
MEGABITS = 10 ** 6
Y_FRACT = 0.5
X_FRACT = 0.8

net = None

## Should be run in python3.8
class TreeTopo(Topo):
    def build(self, topo_file: str = TOPO_INPUT_FILE):
        with open(file=topo_file, mode="r") as f:
            N, M, L = map(int, f.readline().split())

            for i in range(1, N + 1):
                self.addHost(name=f"h{i}")

            for i in range(1, M + 1):
                self.addSwitch(name=f"s{i}", dpid="%016x" % i)

            for _ in range(L):
                dev1, dev2, bw = map(str.strip, f.readline().split(","))
                self.addLink(node1=dev1, node2=dev2, bw=int(bw))


def startNetwork():
    info("** Creating the tree network\n")
    topo = TreeTopo()

    global net
    net = Mininet(
        topo=topo,
        link=Link,
        controller=lambda name: RemoteController(name, ip=CONTROLLER_IP),
        listenPort=CONTROLLER_PORT,
        autoSetMacs=True,
    )

    info("** Starting the network\n")
    net.start()

    ## set up QoS queues
    switches: set[OVSKernelSwitch] = set(net.switches)
    for switch in switches:
        interfaces: list[Intf] = switch.intfList()
        for interface in interfaces:
            link: Optional[Link] = interface.link
            if link is None or (
                link.intf1.node in switches and link.intf2.node in switches
            ):
                continue

            bw = (
                topo.linkInfo(link.intf1.node.name, link.intf2.node.name).get("bw")
                * MEGABITS
            )
            Y, X = int(bw * Y_FRACT), int(bw * X_FRACT)

            os.system(
                f"sudo ovs-vsctl -- set Port {interface.name} qos=@newqos \
                -- --id=@newqos create QoS type=linux-htb other-config:max-rate={bw} queues=0=@q0,1=@q1 \
                -- --id=@q0 create queue other-config:max-rate={Y} \
                -- --id=@q1 create queue other-config:min-rate={X}"
            )

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
