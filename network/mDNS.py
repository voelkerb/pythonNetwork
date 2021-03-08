"""File which handles Network connections."""

import sys
import os
# Import top level module
try:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    root = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
sys.path.append(root)

import time
import threading
import subprocess
import socket
import platform
import signal
from .basher import Basher
from zeroconf import ServiceBrowser, Zeroconf, ServiceInfo

class mDNSListener:

    def __init__(self):
        self.deviceList = []

    def remove_service(self, zeroconf, type, name):
        print("Service %s removed" % (name,))
        self.deviceList = [dev for dev in self.deviceList if name not in str(dev[0].split(".")[0])]

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        self.deviceList.append((str(info.server).rstrip("."), str(socket.inet_ntoa(info.address)), info.port))
        print("Service %s added, service info: %s" % (name, info))


class mDNS():
    """Class which finds mDNS services and IP addresses associated to them."""

    #: Standard wait time for dns -sd call to show all results
    STANDARD_BONJOUR_WAITTIME = 5.0
    #: Standard wait time for avahi command to show results
    STANDARD_AVAHI_WAITTIME = 0.5
    #: Standard time to wait for ping cmd to finish
    STANDARD_PING_WAITTIME = 1.0

    # Init function
    def __init__(self):
        """
        Init the mDNS discovery service
        """
        #: | default: None
        #: | Service names of hosted services. Add with :func:`announce <network.mDNS.mDNS.announce>`
        self.services = []
        self._zeroconf = Zeroconf()
        pass

    def pingResolve(self, ip, verbose=False, waittime=1.0):
        """
        Resolve a mdns name using a system ping request.

        :param   ip: MDNS name to resolve e.g. esp32.local
        :type    ip: str
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for ping to succeed or fail
        :type    waittime: float, default: 1.0

        :return: Tuple of the form (reachabel, ip address)
        :rtype: tuple(bool, str)
        """
        if waittime == -1:
            waittime = self.STANDARD_PING_WAITTIME
        command = "ping -c 2 -t 2 -i " + str(waittime)   + " " + str(ip)
        basher = Basher(command, waittime=waittime, echo=verbose)
        output = basher.run(wait=False)
        while time.time()-basher.startTime < waittime and len(output) < 2:
            time.sleep(0.01)
        basher.stop()
        if len(output) < 2: return False, ip
        for out in output[1:]:
            if " bytes from " in out:
                rip = out.split(" bytes from ")[-1].split(" ")[0].rstrip(":")
                return True, rip
        return False, ip

    def ping(self, ip, verbose=False, waittime=1.0):
        """
        Simple ping to see if device is available.

        :param   ip: MDNS name to resolve e.g. esp32.local
        :type    ip: str
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for ping to succeed or fail
        :type    waittime: float, default: 1.0

        :return: ``True`` on reachable
        :rtype: bool
        """
        success, _ = self.pingResolve(ip, verbose=verbose, waittime=waittime)
        return success


    def getInstancesForServiceNames(self, mDNS_serivceName, serviceType, waittime=-1, verbose=False):
        """
        Returns all mDNS entries for a particular service name and type

        :param   mDNS_serivceName:  Service name to discover. Underscore is handled (use it or leave it).
        :type    mDNS_serivceName:  str
        :param   serviceType:       Service type. Typically _tcp or _udp. Underscore is handled (use it or leave it).
        :type    serviceType:       str
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for new entries
        :type    waittime: float, default: :attr:`STANDARD_BONJOUR_WAITTIME<network.mDNS.mDNS.STANDARD_BONJOUR_WAITTIME>` or :attr:`STANDARD_AVAHI_WAITTIME<network.mDNS.mDNS.STANDARD_AVAHI_WAITTIME>`

        :return: List of instance names with \".local\" attached. e.g. esp32.local
        :rtype: list
        """
        _serviceName = "_" + mDNS_serivceName.lstrip("_")
        _serviceType = "_" + serviceType.lstrip("_")
        # Either browse with avahi or bonjour 
        bonjour = False
        if platform.system() == 'Darwin': bonjour = True
        if bonjour: command = "dns-sd -B " + str(_serviceName) + "." + _serviceType
        else: command = "avahi-browse " + str(_serviceName) + "." + _serviceType

        if waittime == -1:
            if bonjour: waittime = self.STANDARD_BONJOUR_WAITTIME
            else: waittime = self.STANDARD_AVAHI_WAITTIME

        basher = Basher(command, waittime=waittime, echo=verbose)
        output = basher.run(wait=False)
        while time.time()-basher.startTime < waittime:
            time.sleep(0.1)
        basher.stop()
        if bonjour:
            #  First lines are info
            if len(output) < 5: return []
            # Cut info
            else: output = output[4:] 
            instances = [out.split("  ")[-1].rstrip("\n") + ".local" for out in output]
        else:
            instances = [out.split("IPv4 ")[-1].split("  ")[0] + ".local" for out in output]

        return instances

    def getIPsForInstances(self, instances, waittime=-1.0, verbose=False):
        """
        Returns ip addresses for a list of instances (<devicename>.local) if these are reachable.

        The reachability check is performed with a ping request. 

        :param   instances:  List of instance names (e.g. esp32.local)
        :type    instances:  list[str]
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for new entries
        :type    waittime: float, default: :attr:`STANDARD_BONJOUR_WAITTIME<network.mDNS.mDNS.STANDARD_BONJOUR_WAITTIME>` or :attr:`STANDARD_AVAHI_WAITTIME<network.mDNS.mDNS.STANDARD_AVAHI_WAITTIME>`

        :return: List of tuples (hostname, ip address)
        :rtype: list
        """
        devices = []    
        bonjour = False
        if platform.system() == 'Darwin': bonjour = True
        if bonjour:
            if waittime == -1:
                waittime = self.STANDARD_BONJOUR_WAITTIME
            if instances is None: return None
            bashers = []
            starttime = time.time()
            for host in instances:
                basher = Basher("dns-sd -q " + host, waittime=waittime, echo=verbose)
                bashers.append(basher)
                basher.run(wait=False)

            while time.time()-starttime < waittime:
                for basher in bashers:
                    if len(basher.output) > 2: basher.stop()
                if all(len(basher.output) > 2 for basher in bashers): break
            for host, basher in zip(instances, bashers):
                basher.stop()
                # print("*********")
                # print(basher.output)
                # print("*********")
                if len(basher.output) >= 3:
                    ip = basher.output[-1].split("  ")[-1].rstrip("\n").replace(" ","")
                    devices.append((host, ip))
        else:
            for instance in instances:
                success, ip = self.pingResolve(instance)
                if success: devices.append((instance, ip))

        return devices

    def getDevicesForServiceNamesAvahi(self, mDNS_serivceName, serviceType, waittime=-1, verbose=False):
        """
        Returns all mDNS entries for a particular service name and type

        :param   mDNS_serivceName:  Service name to discover. Underscore is handled (use it or leave it).
        :type    mDNS_serivceName:  str
        :param   serviceType:       Service type. Typically _tcp or _udp. Underscore is handled (use it or leave it).
        :type    serviceType:       str
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for new entries
        :type    waittime: float, default: :attr:`STANDARD_AVAHI_WAITTIME<network.mDNS.mDNS.STANDARD_AVAHI_WAITTIME>`

        :return: List of tuples (hostname, ip address)
        :rtype: list[(str, str)]
        """
        _serviceName = "_" + mDNS_serivceName.lstrip("_")
        _serviceType = "_" + serviceType.lstrip("_")
        # We use avahi here
        command = "avahi-browse " + str(_serviceName) + "." + _serviceType + " -r"
        if waittime == -1: waittime = self.STANDARD_AVAHI_WAITTIME

        basher = Basher(command, waittime=waittime, echo=verbose)
        output = basher.run(wait=False)
        while time.time()-basher.startTime < waittime:
            time.sleep(0.1)
        basher.stop()
        output = [line for line in output if "+" not in line[:2]]
        output = [line for line in output if "hostname =" in line or "address =" in line]
        devices = []
        #  give me each seconds element
        for i in range(0, len(output), 2):
            host = output[i][output[i].find("[")+1:output[i].find("]")]
            ip = output[i+1][output[i+1].find("[")+1:output[i+1].find("]")]
            devices.append((host, ip))
        return devices

    def parallelPingResolve(self, instances, waittime=-1.0, verbose=False):
        """
        Ping instances in parallel, is much quicker than sequential.

        :param instances: List of hostnames or ip adresses
        :type  instances: str
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for new entries
        :type    waittime: float, default: :attr:`STANDARD_PING_WAITTIME<network.mDNS.mDNS.STANDARD_PING_WAITTIME>`

        :return: List of tuples (reachable, ip address)
        :rtype: list[(bool, str)]
        """
        if len(instances) == 0: return []
        results = []
        if waittime == -1:
            waittime = self.STANDARD_PING_WAITTIME
        bashers = [Basher("ping -c 2 -t 2 -i " + str(waittime) + " " + str(instance), waittime=waittime, echo=verbose) for instance in instances] 
        for basher in bashers:
            basher.run(wait=False)
        start = time.time()
        finished = False
        while time.time()-start < waittime and not finished:
            finished = True
            for basher in bashers:
                if basher.running and len(basher.output) >= 2:
                    basher.stop()
                else:
                    finished = False
            time.sleep(0.001)
        
        for basher, ip in zip(bashers, instances):
            if len(basher.output) < 2: 
                results.append((False, ip))
            else:
                found = False
                for out in basher.output[1:]:
                    if " bytes from " in out:
                        rip = out.split(" bytes from ")[-1].split(" ")[0].rstrip(":")
                        results.append((True, rip))
                        found = True
                        break
                if not found:
                    results.append((False, ip))

        return results            

    def searchForService(self, mDNS_serivceName, serviceType, reachable=True, waittime=-1.0, verbose=False):
        """
        Start searching for mDNS services on the network.

        :param mDNS_serivceName: The Service to search for.
        :type  mDNS_serivceName: str
        :param serviceType: The service type: e.g. tcp or udp or ssh.
        :type  serviceType: str
        :param   reachable: If set to ``True`` only reachable devices are returned
        :type    reachable: bool, default: True
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        :param   waittime: Time to wait for new entries
        :type    waittime: float, default: :attr:`STANDARD_BONJOUR_WAITTIME<network.mDNS.mDNS.STANDARD_BONJOUR_WAITTIME>` or :attr:`STANDARD_AVAHI_WAITTIME<network.mDNS.mDNS.STANDARD_AVAHI_WAITTIME>`

        :return: List of tuples (hostname, ip address)
        :rtype: list[(str, str)]
        """
        devices = []
        bonjour = False
        if platform.system() == 'Darwin': bonjour = True
        if bonjour:
            instances = self.getInstancesForServiceNames(mDNS_serivceName, serviceType, waittime=waittime, verbose=verbose)
            if instances is None or len(instances) == 0: return []
            if verbose: 
                print("Resolving Ip for: ")
                for instance in instances:
                    print("\t" + instance)
            results = self.parallelPingResolve(instances, waittime=waittime, verbose=verbose)
            for instance, result in zip(instances, results):
                success, ip = result
                if success or not reachable: devices.append((instance, ip))
                else: 
                    if verbose:
                        print("cannot find: " + instance)

            # devices = self.getIPsForInstances(instances, waittime=waittime, verbose=verbose)
            # if devices is None or len(instances) == 0: return []
            # if len(instances) != len(devices):
            #     devices = self.getIPsForInstances(instances, waittime=waittime/2)
        else:
            devices = self.getDevicesForServiceNamesAvahi(mDNS_serivceName, serviceType, waittime=waittime, verbose=verbose)
            
        return devices

    def resolveHost(self, hostname, verbose=False):
        """
        Resolves a hostname to an ip address using system call of \"host (m)DNSName\"

        :param hostname: The hostname which should be resolved
        :type  hostname: str
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        
        :return: ip address or None if not found
        :rtype: str or None
        """
        # Check if hostname is already a valid ip address
        try:
            socket.inet_pton(socket.AF_INET, hostname)
        except AttributeError:  # no inet_pton here, sorry
            try:
                socket.inet_aton(hostname)
            except socket.error:
                pass
            if hostname.count('.') == 3:
                return hostname
        except socket.error:  # not a valid address
            pass
        if hostname.count('.') == 3:
            return hostname

        # Else check result of host call
        command = "host " + str(hostname)
        basher = Basher(command, echo=verbose)
        output = basher.run()
        if len(output) < 1:
            return None
        output = [out for out in output if "address " in out]
        if len(output) > 0: return output[0].split("address ")[-1].rstrip("\n")
        else: return None

    def resolveNames(self, names, verbose=False):
        """
        Resolves a a list of hostnames using system call of \"host (m)DNSName\"

        :param names: List of hostnames
        :type  names: list
        :param   verbose: If set to ``True`` the output of the ping request is shown on console
        :type    verbose: bool, default: False
        
        :return: List of tuples (hostname, ip address)
        :rtype: list[(str,str)]
        """
        resolved = []
        for name in names:
            ip = self.resolveHost(name, verbose=verbose)
            if ip is not None:
                resolved.append([name, ip])
        return resolved

    def get_local_address(self):
        """
        Get the ip address of the machine. (Needs internet access).
        
        :return: IP address of the machine
        :rtype: str or None
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("www.amazon.com", 80))
        res = s.getsockname()[0]
        s.close()
        return res

    def announce(self, hostName, serivceName, serviceType, address, port, desc={}):
        """
        Announce a mDNS service on the network using `zeroconf <https://python-zeroconf.readthedocs.io/>`_.

        :param hostName:    Name of our host
        :type  hostName:    str
        :param serivceName: Name of the service to announce
        :type  serivceName: str
        :param serviceType: Type of this service
        :type  serviceType: str
        :param address: IP Address at which the service is hosted
        :type  address: str
        :param port:    Port on which the service is hosted
        :type  port:    int
        :param desc:    dictionary describing the use of the system. One entry is an entry in mDNS  
        :type  desc:    dict, default=``{}``
        """
        serivceName = "_" + serivceName.lstrip("_")
        serviceType = "_" + serviceType.lstrip("_")
        hostName = "_" + hostName.lstrip("_")
        service =  str(serivceName + "." + serviceType + ".local.")
        # print("Registering: " + str(service))
        if address == "0.0.0.0":
            address = self.get_local_address()
            print(address)
        info = ServiceInfo(service,
                           hostName + " ." + service,
                           socket.inet_aton(address), port, 0, 0,
                           desc, hostName + ".local.")
        self.services.append(info)
        self._zeroconf.register_service(info)

    def __del__(self):
        """On delete, the system should unregister registered mDNS entries"""
        for service in self.services:
            # print("Unregistering...")
            # print(service)
            self._zeroconf.unregister_service(service)


def initParser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostName", type=str, default="networkMeter",
                        help="Host name for service")
    parser.add_argument("-n", "--serviceName", type=str, default="_elec",
                        help="Service name to search for")
    parser.add_argument("-t", "--serviceType", type=str, default="_tcp",
                        help="Service type to search for")
    parser.add_argument("-w", "--waittime", type=float, default=5.0,
                        help="How long to wait")
    parser.add_argument("-p", "--port", type=int, default=23456,
                        help="Port on which to announce")
    parser.add_argument("-i", "--ip", type=str, default="0.0.0.0",
                        help="Port on which to announce")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase output verbosity")
    return parser


# _______________Can be called as main__________________
if __name__ == '__main__':
    import os
    parser = initParser()
    args = parser.parse_args()


    mdns = mDNS()
    possibleHosts = ["powermeter" + str(i) + ".local" for i in range(20)]
    devices = mdns.resolveNames(possibleHosts, verbose=args.verbose > 0)
    print(devices)
    devices = mdns.searchForService(args.serviceName, args.serviceType, waittime=args.waittime, verbose=args.verbose > 0)
    print(devices)

    mdns.announce(args.hostName, args.serviceName, args.serviceType, args.ip, args.port)
    zeroconf = Zeroconf()
    listener = mDNSListener()
    browser = ServiceBrowser(zeroconf, "_" + args.serviceName.lstrip("_") + "." + "_" + args.serviceType.lstrip("_") + ".local.", listener)
    try:
        input("Press enter to exit...\n\n")
    finally:
        zeroconf.close()
    print("Bye Bye from " + str(os.path.basename(__file__)))
