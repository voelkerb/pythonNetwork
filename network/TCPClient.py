"""
Copyright: Benjamin Völker
eMail: voelkerb@me.com
License: MIT

Simple TCP Client
"""

import sys
import os
import time
import argparse
from network import NetworkClient
try:
    import gnureadline as readline
except ImportError:
    import readline



def inputFromClient(msg, client):
    print("\r<" + client.TCP_IP + ": ", end="")
    print(msg.decode("utf-8"))
    print("\n>" + str(client.TCP_IP) + "$ ", end="")
    pass

def initParser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default="networkMeter",
                        help="Host name for service")
    parser.add_argument("-p", "--port", type=int, default=54321,
                        help="Port on which to announce")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")
    return parser

# _______________Can be called as main__________________
if __name__ == '__main__':
    parser = initParser()
    args = parser.parse_args()

    client = NetworkClient(port=args.port, ip=args.ip, incomingHandler=inputFromClient, withLengthPrefix=False, lines=True)
    client.connect()
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            break

        if not line:
            continue
        line = line.rstrip("\n")
        line = line.rstrip("\r")
        print(line)
        client.sendMsg(line)

    print("Bye Bye from " + str(os.path.basename(__file__)))
