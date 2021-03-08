"""
Copyright: Benjamin Völker
eMail: voelkerb@me.com
License: MIT

Simple TCP Server
"""
import argparse
import sys
import time
import signal
import os
from network import NetworkServer, ClientHandler

PREFIX = ""
ECHO = False

def request(addr, msg, clientHandler):
    try:
        line = msg.decode("utf-8").replace("\r", "").replace("\n", "")
    except:
        line = str(msg)
    print(str(addr) + ": " + str(line))
    if ECHO:
        lineBack = PREFIX + str(line)
        clientHandler.sendMsg(lineBack)

def initParser():
    parser = argparse.ArgumentParser(description="Creates a simple TCP server. Sent messages are shown and can be echoed back.")
    parser.add_argument("--ip", type=str, default="0.0.0.0",
                        help="Hostname or IP address of server, default: \"0.0.0.0\"")
    parser.add_argument("--port", type=int, default=54321,
                        help="Port, default: 54321.")
    parser.add_argument("--echo", action="store_true", 
                        help="Echo received back")
    parser.add_argument("--prefix", type=str, default="",
                        help="Prefix send infront of data")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")
    return parser
                        
# _______________Can be called as main__________________
if __name__ == '__main__':
    parser = initParser()
    args = parser.parse_args()

    net = NetworkServer(port=args.port, ip=args.ip, requestHandler=request)
    net.startServer()

    PREFIX = args.prefix
    ECHO = args.echo

    # Catch control+c
    running = True
    # Get external abort
    def aborted(signal, frame):
        global running
        running = False
    signal.signal(signal.SIGINT, aborted)

    while(running):
        time.sleep(0.1)
        # net.broadcastMessage("{\"method\":\"poll\",\"id\":\"ESP32\"}")
    net.stopServer()

    print("Bye Bye from " + str(os.path.basename(__file__)))
