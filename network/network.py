"""
Copyright: Benjamin Völker
eMail: voelkerb@me.com
License: MIT

File which handles Network connections.

We have 5 different classes in this File. Decide the class you need:


NetServer:      Simple TCP server with an update method and callbacks.
NetClient:      Handles clients of a NetServer with receive and send method.
NetworkServer:  TCP server with thread for handling incoming connections.
ClientHandler:  Handles clients of a NetworkServer with threads for sending and receiving.
NetworkClient:  TCP client that connects to a TCP server.
"""
import socket
import select
import threading
import sys
import struct
import time
from retrying import retry
from queue import Queue

DEBUG = False
ECHO_BACK = False

class NetServer():
    """
    Class for a simple tcp server.

    Using this module is as easy as:
    
    .. code-block:: python3

        netServer = NetServer("0.0.0.0", 54321)
        netServer.start()
        netClients = []
        while True:
            netClient = netServer.update()
            if netClient is not None:
                netClient.sendMsg("Hello")
                netClients.append(netClient)
            time.sleep(1.0)
        netServer.stop()

    Simple TCP Server. Connected sockets are returned in update method.
    Or if updated in thread use cb.
    Alternatively you can pass a CB.
    """

    def __init__(self, address, port, connectedCallback=None, logger=print, updateInThread=False):
        """
        Init the Network class.

        :param address: Ip-adress
        :type  address: str
        :param port:    The port on which the server should listen
        :type  port:    int
        :param connectedCallback: Optional CB when clients connect
        :type  connectedCallback: function
        """
        self.logger = logger
        self.address = address
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = []
        self.connectedCallback = connectedCallback
        self.updateInThread = updateInThread
        self._running = False
        self._updateThread = threading.Thread(target=self._update, daemon=True)


    def start(self):
        """ Start the TCP Server. """
        self.server.bind((self.address, self.port))
        # start listening for clients
        self.server.listen(5)
        self.server.setblocking(0)
        if self.logger: self.logger("+++ Server listening on port %i" % self.port)
        if self.updateInThread:
            self._running = True
            self._updateThread.start()

    def stop(self):
        self._running = True
        if self.logger: self.logger("Stopping Server")
        if self.updateInThread:
            # Will not work because of blocking select call
            # self._updateThread.join()
            pass
        self.server.close()

    def _update(self):
        while self._running:
            self.update()
            time.sleep(0.1)

    def update(self):
        """
        Update the server.

        :return: Client connected or None
        :rtype:  NetClient
        """
        try:
            readable, writable, errored = select.select([self.server], [], [], 0)
        except ValueError:
            # The server was closed during above blocking call
            return None
        for s in readable:
            if s is self.server:
                clientSock, addr = self.server.accept()
                client = NetClient(clientSock, addr[0], addr[1], logger=self.logger)
                if self.connectedCallback: self.connectedCallback(client)
                return client
        return None


class NetClient():
    """
    Class which handles a single tcp client.

    This class uses no threads, instead you have to call an update method in a loop.
    An equivalent class without threads is down below.
    """

    # Init function
    def __init__(self, clientsocket, address, port, disconnectedCallback=None, logger=print):
        """
        Init the netclient.

        :param clientsocket: The socket the client reads from and writes to
        :type  clientsocket: socket
        :param address:      The address of the given socket
        :type  address:      str
        :param port:         The port of the given socket
        :type  port:         int
        """
        self.logger = logger
        self.sock = clientsocket
        self.address = address
        self.port = port
        self.connected()
        self.sock.setblocking(0)
        self.receiveBuffer = b''
        self.send_queue = Queue(maxsize=0)
        self.send_data = b''
        self.disconnectedCallback = disconnectedCallback

    def connected(self):
        """ Is called in init to indicate connection. """
        if self.logger: self.logger("Client with address: %s connected at port %s" % (self.address, str(self.port)))

    def disconnected(self):
        """ Is called when the client disconnects, CB is notified. """
        if self.logger: self.logger("Client with address: %s disconnected" % (self.address))
        if self.disconnectedCallback: self.disconnectedCallback(self)

    def sendMsg(self, msg, blocking=False):
        """
        Send message over the socket.

        :param msg:      The message to send to the client, r""r r""n is added.
        :type  msg:      str:
        :param blocking: If the msg should be send blocking or non blocking.
        :type  blocking: bool, default=False
        """
        reply = bytes(msg + "\r\n", 'utf-8')
        self.sendData(reply, lengthPrefix=False, blocking=blocking)

    def sendData(self, data, lengthPrefix=False, blocking=False):
        """
        Send data over the socket.

        :param msg:          The message to send to the client, r""r r""n is added.
        :type  msg:          str
        :param blocking:     If the msg should be send blocking or non blocking.
        :type  blocking:     bool, default=False
        :param lengthPrefix: If the msg should be send blocking or non blocking.
        :type  lengthPrefix: bool, default=False
        """
        s_data = b''
        if lengthPrefix: s_data = struct.pack('!I', len(data))
        s_data += data
        if blocking:
            try:
                self.sock.sendall(s_data)
            except socket.error as err:
                if self.logger: self.logger("Send failed. Error: %s" % str(err))
                if isinstance(err.args, tuple):
                    # Broken Pipe error
                    if err.errno == 11:
                        if self.logger: self.logger("ignoring..")
                    else: self.close()
                else: self.close()
        else:
            self.send_queue.put(s_data)

    def isSending(self):
        """
        Returns true if sendbuffer is non empty.

        :return: If still sth in send buffer
        :rtype:  bool
        """
        return len(self.send_data) > 0 or not self.send_queue.empty()

    def handleSend(self):
        """ Function handling the sending. """
        # handle non blocking sending
        if len(self.send_data) > 0:
            try:
                sent = self.sock.send(self.send_data)
                self.send_data = self.send_data[sent:]
            except socket.error as err:
                if self.logger: self.logger("Send failed. Error: %s" % str(err))
                if isinstance(err.args, tuple):
                    # Broken Pipe error
                    if err.errno == 11: 
                        if self.logger: self.logger("ignoring..")
                    else: self.close()
                else: self.close()
        else:
            if not self.send_queue.empty():
                self.send_data = self.send_queue.get()
                self.send_queue.task_done()

    def available(self, timeout=0):
        """
        Returns true if data is available to read.

        :param timeout: Optional timeout parameter for waiting.
        :type  timeout: float
        :return: If data is available to be read
        :rtype:  bool
        """
        ready_to_read, ready_to_write, in_error = select.select([self.sock], [], [self.sock], timeout)
        return len(ready_to_read) > 0 or len(self.receiveBuffer) != 0

    def receive(self, msgLen=512):
        """
        Returns true if data is available to read.

        :param msgLen: Optional msg length to be read. It will however stop if a newline char is found.
        :type  msgLen: int
        :return: Data which is read. b'' if nothing is read, None if client disconnected.
        :rtype:  binary data
        """
        bytesRcvd = 0
        msg = b''
        try:
            while bytesRcvd < msgLen:
                chunk = self.sock.recv(msgLen - bytesRcvd)
                if not chunk and len(self.receiveBuffer) == 0:
                    self.disconnected()
                    return None
                bytesRcvd += len(chunk)
                self.receiveBuffer += chunk
                index = self.receiveBuffer.find(b'\n')
                if index:
                    msg = self.receiveBuffer[:index+1]
                    self.receiveBuffer = self.receiveBuffer[index+1:]
                    break
            return msg
        except socket.error:
            self.disconnected()
            # indicate that socket is dead
            return None


class NetworkServer():
    r"""
    Class for a more advanced tcp server.

    Using this module is as easy as:

    .. code-block:: python3

        net = NetworkServer(port=54321, ip="0.0.0.0", requestHandler=handlerFunction)
        net.startServer()
        while True:
            net.broadcastMessage("Hello all")
            time.sleep(1.0)
        net.stopServer()

    Can be singleton, using threads for incoming clients. Can broadcast data to all
    Clients. You can pass a CB to be notified when clients connect.
    """
    # Here will be the instance stored.
    __instance = None
    @staticmethod
    def getInstance(port=2000, ip='127.0.0.1', requestHandler=None, logger=print):
        """ Static access method. """
        if SingletonNetwork.__instance == None:
            NetworkServer(port=port, ip=ip, requestHandler=requestHandler, singleton=True, logger=logger)
        return SingletonNetwork.__instance

    def __init__(self, port=2000, ip='127.0.0.1', requestHandler=None, singleton=False, logger=print):
        """
        Init the Network class.

        :param port: The port on which the server should listen
        :type  port: int
        :param ip: Ip-adress
        :type  ip: str
        :param reqestHandler:
            Callback, that is called when a tcp client senda a requenst.
            Parameters are adress, message and object of class ClientHandler
        :type  reqestHandler: function
        """

        """ Virtually private constructor. """
        if singleton:
            if NetworkServer.__instance != None:
                raise Exception("This class is a singleton!")
            else:
                NetworkServer.__instance = self
        self.logger = logger
        # Set IP to localhost
        # port can be chosen by the user
        self.TCP_IP = ip
        self.TCP_PORT = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clientHandlers = []
        self.running = False
        self.thread = threading.Thread(target=self.__handleClients)
        self.thread.daemon = True
        self.requestHandlers = []
        if requestHandler is not None:
            self.requestHandlers.append(requestHandler)

    def addRequestHandler(self, reqHandler):
        """
        Add a reqeusthandler.

        :param reqestHandler:
            Callback, that is called when a tcp client senda a requenst.
            Parameters are adress, message and object of class ClientHandler
        :type  reqestHandler: function
        """
        if reqHandler in self.requestHandlers:
            return
        self.requestHandlers.append(reqHandler)
        # Add it to all clienthandlers as well
        for ch in self.clientHandlers:
            ch.requestHandlers.append(reqHandler)

    def removeRequestHandler(self, reqHandler):
        """
        Add a reqeusthandler.

        :param reqestHandler:
            Callback, that is called when a tcp client senda a requenst.
            Parameters are adress, message and object of class ClientHandler
        :type  reqestHandler: function
        """
        if reqHandler not in self.requestHandlers:
            return
        # Add it to all clienthandlers as well
        for ch in self.clientHandlers:
            if reqHandler in ch.requestHandlers:
                ch.requestHandlers.remove(reqHandler)
        self.requestHandlers.remove(reqHandler)

    def startServer(self):
        """
        Call to start the server.

        This function will start the tcp server on the specified port.
        An exception is called if the socket fails to open.
        """
        # start server at given ip adress and port
        try:
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.TCP_IP, self.TCP_PORT))
            # start listening for clients
            self.server.listen(5)

            if self.logger: self.logger("+++ Server listening on port %i" % self.TCP_PORT)

            self.running = True
            self.thread.start()

        except socket.error as msg:
            if self.logger: self.logger("Bind failed. Error: %s" % str(msg))
            sys.exit()

    def stopServer(self):
        """
        Call to stop the server.

        This function will stop the tcp server if it was running before
        by simply setting a flag such that the thread handle function will
        not break its while statement.
        """
        self.running = False
        if self.logger: self.logger("Stopping Server")
        # Wait for thread to finish
        self.thread.join()

    def broadcastData(self, data, lengthPrefix=False):
        """
        Call to broadcast raw data to all clients.

        :type  data: binary data
        :param data: the data send to all clients
        """
        for ch in self.clientHandlers:
            if ch.running is True:
                ch.sendData(data, lengthPrefix=lengthPrefix, blocking=False)

    def broadcastMessage(self, msg):
        """
        Call to broadcast a message to all clients.

        :param msg: The message to send to all clients
        :type  msg: str
        """
        for ch in self.clientHandlers:
            if ch.running is True:
                ch.sendMsg(msg)

    def __closeAll(self):
        """
        Call to stop all sockets.

        This function will stop the server as well as all socket connections.
        """
        # close all client connections on destroy
        self.server.close()
        for ch in self.clientHandlers:
            ch.close()
        if self.logger: self.logger("Server and Clients released")

    def __handleClients(self):
        """
        Call to handle all incoming tcp connections.

        This function handles all socket connections, opens instances of
        clienthandlers and starts/stops their threads.
        """
        while self.running is True:
            read_list = [self.server]
            readable, writable, errored = select.select(read_list, [], [], 0.5)
            for s in readable:
                if s is self.server:
                    c, addr = self.server.accept()
                    ch = ClientHandler(c, addr)
                    ch.requestHandlers.extend(self.requestHandlers)
                    ch.handle()
                    if DEBUG:
                        if self.logger: self.logger("Client added")
                    self.clientHandlers.append(ch)
            # Poll clients for disconnect state after select timeout
            # If the client is not connected, delete the  clienthanasdler
            # instance
            for ch in self.clientHandlers:
                if ch.running is False:
                    ch.close()
                    self.clientHandlers.remove(ch)

        self.__closeAll()


class ClientHandler():
    """
    Class which handles a single tcp client.

    This class uses two threads, one for receiving data and one for sending data non-blocking.
    An equivalent class without threads is down below.
    """

    # Init function
    def __init__(self, clientsocket, addr, logger=print):
        """
        Init the tcp client handler.

        :param clientsocket: The socket the client reads from and writes to
        :type  clientsocket: socket
        :param addr:
            list containing the host as a string and the and the port as a
            number [host, port]
        :type  addr: list [string, number]
        """
        self.logger = logger
        self.csocket = clientsocket
        # Set IP to localhost
        # port can be chosen by the user
        self.addr = addr
        self.clientConnected()
        self.running = False
        self.thread = threading.Thread(target=self.__handleClient, args=())
        self.sendThread = threading.Thread(target=self.__handleSend, args=())
        self.thread.daemon = True
        self.sendThread.daemon = True
        self.requestHandlers = []
        # give me a send_queue of maximum size
        self.send_queue = Queue(maxsize=0)
        self.send_data = b''

    def handle(self):
        """
        Start handling the client thread.

        The thread which is starte in this method must be closed using the
        close() function below. If this method is not called after init
        messages will not be received.
        """
        # Set Running flag
        self.running = True
        # Start the client handling in new thread
        self.thread.start()
        self.sendThread.start()

    def close(self):
        """Close the socket connection."""
        # Reset handling thread. Correct abort is treted in
        # __handleClient function
        if DEBUG:
            if self.logger: self.logger("Closing connection to %s" % self.addr[0])
        self.running = False
        # Wait for thread to finish
        self.sendThread.join()
        self.thread.join()

    def clientConnected(self):
        """
        Call if a client connects to the TCP server.

        Init stuff can be done here
        """
        if self.logger: self.logger("Client with address: %s connected at port %s"
                                    % (self.addr[0], str(self.addr[1])))
        # Do specific init stuff if the client connects

    def sendMsg(self, msg, blocking=True):
        """
        Send message over the socket.

        :param msg:      The message to send to the client, r""r r""n is added.
        :type  msg:      str:
        :param blocking: If the msg should be send blocking or non blocking.
        :type blocking:  bool, default=True
        """
        reply = bytes(msg + "\r\n", 'utf-8')
        # send reply
        self.sendData(reply, lengthPrefix=False, blocking=blocking)

    def __sendDataBlocking(self, data, lengthPrefix=False):
        """
        Send the given data blocking.

        :param data:         The data to send to the client.
        :type  data:         data
        :param lengthPrefix: If True, a 4 byte integer with the length of the data is sent leading the data.
        :type lengthPrefix:  bool, default=False
        """
        try:
            s_data = b''
            if lengthPrefix: s_data = struct.pack('!I', len(data))
            s_data += data
            self.csocket.sendall(s_data)
        except socket.error as err:
            if self.logger: self.logger("Send failed. Error: %s" % str(err))
            if isinstance(err.args, tuple):
                # Broken Pipe error
                if err.errno == 11: 
                    if self.logger: self.logger("ignoring..")
                else: self.close()
            else: self.close()

    def sendData(self, data, lengthPrefix=False, blocking=True):
        """
        Send the given data either blocking or non blocking.

        :param data:         The data to send to the client.
        :type  data:         data
        :param blocking:     If the msg should be send blocking or non blocking.
        :type  blocking:     bool, default=True
        :param lengthPrefix: If True, a 4 byte integer with the length of the data is sent leading the data.
        :type  lengthPrefix: bool, default=False
        """
        if blocking:
            self.__sendDataBlocking(data, lengthPrefix=lengthPrefix)
        else:
            s_data = b''
            if lengthPrefix: s_data = struct.pack('!I', len(data))
            s_data += data
            self.send_queue.put(s_data)

    def __handleSend(self):
        """
        Thread function to handle non-blocking sending of the data.

        The while loop can be broken using NetworkClient.close() method
        """
        # While running flag is set
        while self.running is True:
            # handle non blocking sending
            if len(self.send_data) > 0:
                try:
                    sent = self.csocket.send(self.send_data)
                    self.send_data = self.send_data[sent:]
                except socket.error as msg:
                    if self.logger: self.logger("Send failed. Error: %s" % str(msg))
            else:
                if not self.send_queue.empty():
                    self.send_data = self.send_queue.get()
                    self.send_queue.task_done()
                else:
                    # Prevent 100% CPU
                    time.sleep(0.01)

    def __handleClient(self):
        """
        Thread function to handle non-blocking receiving of the data.

        The while loop can be broken using NetworkClient.close() method
        """
        # We don't want recv to be blocking because we want to be able
        # to stop the thread. So we define a timeout after which the
        # recv() function will return. Error/Data/noData is handled
        self.csocket.settimeout(0.5)
        # While running flag is set
        while self.running is True:
            # handle non blocking reading
            try:
                msg = self.csocket.recv(1024)
                if len(msg) > 2:
                    if self.logger and DEBUG:
                        self.logger("%s >>  %s" % (self.addr[0], msg))
                    for rh in self.requestHandlers:
                        rh(self.addr[0], msg, self)
                    if ECHO_BACK and len(self.requestHandlers) < 1:
                        reply = bytes("Return: ", 'utf-8') + msg.upper()
                        # send reply
                        self.sendData(reply)
                else:
                    if self.logger and DEBUG:
                        self.logger("message to short, treat this as a disconnect")
                        # Remote peer disconnected
                        self.logger("Detected remote disconnect")
                    # Reset running flag such that this function
                    # will stop running
                    self.running = False
            # No data yet
            except socket.timeout:
                continue
                # print("Timeout")
            # Catch other errors
            except socket.error as err:
                if isinstance(err.args, tuple):
                    # Broken Pipe error
                    if err.errno == 32:
                        if self.logger and DEBUG:
                            # Remote peer disconnected
                            self.logger("Detected remote disconnect")
                        # Reset running flag such that this function
                        # will stop running
                        self.running = False
                    else:
                        if self.logger: self.logger("errno is %s" % str(err))
                        pass
                else:
                    if self.logger: self.logger("Socket Error: %s" % str(err))
        self.csocket.close()
        if self.logger and DEBUG:
            self.logger("Connection to %s closed" % self.addr[0])




class NetworkClient():
    """
    Class which opens a tcp connection to a server.

    Using this module is as easy as:
    
    .. code-block:: python3

        client = NetworkClient(port=54321, ip="127.0.0.1", incomingHandler=handleInput)
        if client.connect():
            for i in range(5)
                client.sendMsg("Ping: " + str(i))
            client.disconnect()
   
    This class uses a thread for receiving data. The class can be singleton.
    """
    # Here will be the instance stored.
    __instance = None

    @staticmethod
    def getInstance(port=2000, ip='127.0.0.1', incomingHandler=None, logger=print):
        """ Static access method. """
        if NetworkClient.__instance == None:
            NetworkClient(port=port, ip=ip, incomingHandler=incomingHandler, autoReconnect=False, singleton=True, logger=logger)
        return NetworkClient.__instance

    def __init__(self, port=2000, ip='127.0.0.1', incomingHandler=None, autoReconnect=False, singleton=False, logger=print, withLengthPrefix=True, lines=False):
        """
        Init the Network class.

        @type  port: number
        @param port: The port on which the server should listen.
        @type  name: string
        @param name: The name of the thread that is created.
        """

        """ Virtually private constructor. """
        if singleton:
            if NetworkClient.__instance != None:
                raise Exception("This class is a singleton!")
            else:
                NetworkClient.__instance = self

        self.logger = logger
        # Set IP to localhost
        # port can be chosen by the user
        self.TCP_IP = ip
        self.TCP_PORT = port
        self.socket = None
        self.retryThread = None
        self.connected = False
        self.running = False
        self.autoReconnect = autoReconnect
        self.lines = lines
        if self.lines:
            self.thread = threading.Thread(target=self.__handleIncomingLines)
        else:
            self.thread = threading.Thread(target=self.__handleIncoming)
        self.thread.daemon = True
        self.incomingHandlers = []
        self.withLengthPrefix = withLengthPrefix
        if incomingHandler is not None:
            self.incomingHandlers.append(incomingHandler)

    def connect(self, keepRetry=False):
        """
        Call to start the server.

        This function will start the tcp server on the specified port.
        An exception is called if the socket fails to open.
        """
        # start server at given ip adress and port
        if self.connected:
            return True
        try:
            'TODO'
            self.socket = socket.socket()

            if self.logger: self.logger("+++ Client connecting to %s on port %i" % (self.TCP_IP, self.TCP_PORT))
            self.socket.connect((self.TCP_IP, self.TCP_PORT))
            if self.logger: self.logger("+++ Connected +++")
            self.socket.settimeout(0.5)
            self.connected = True
            self.running = True
            self.thread.start()

        except socket.error as msg:
            self.connected = False
            if self.logger: self.logger("Connection failed. Error: %s" % str(msg))
            if not keepRetry:
                raise Exception("Failed to connect to %s on port %i" % (self.TCP_IP, self.TCP_PORT))
            elif keepRetry and self.retryThread is None:
                self.retryThread = threading.Thread(target=self.__retryConnection)
                self.retryThread.daemon = True
                self.retryThread.start()

        return self.connected


    def __retryConnection(self):
        """
        Retrying to connect in new thread.
        Call stack will grow.
        """
        time.sleep(2)
        self.connect(keepRetry=True)
        if not self.connected:
            self.__retryConnection()

    @retry
    def __reconnect(self):
        """
        Reconnect if connection was closed by peer.
        """
        try:
            self.socket = socket.socket()
            if self.logger: self.logger("+++ Client connecting to %s on port %i" % (self.TCP_IP, self.TCP_PORT))
            self.socket.connect((self.TCP_IP, self.TCP_PORT))
            if self.logger: self.logger("+++ Connected +++")
            self.socket.settimeout(0.5)
            self.connected = True
            self.running = True
        except socket.error as msg:
            self.connected = False
            if self.logger: self.logger("Connection failed. Error: %s" % str(msg))
            time.sleep(2)
            raise Exception("Connection failed")

    def disconnect(self):
        """
        Call to stop the server.

        This function will stop the tcp server if it was running before
        by simply setting a flag such that the thread handle function will
        not break its while statement.
        """
        self.running = False
        self.connected = False
        self.socket.close()
        if self.logger: self.logger("Closing Connection")
        # Wait for thread to finish
        self.thread.join()

    def sendMsg(self, msg):
        """
        Call to broadcast a message to all clients.

        @type  msg: string
        @param msg: the message to send to all clients
        """
        self.sendData(str(msg + "\r\n").encode("utf-8"))
        pass

    def sendData(self, data, lengthPrefix=False):
        """
        Call to broadcast a message to all clients.

        @type  msg: string
        @param msg: the message to send to all clients
        """
        s_data = b''
        if lengthPrefix: s_data = struct.pack('!I', len(data))
        s_data += data
        self.socket.sendall(s_data)

    def recvWithLengthPrefix(self):
        lengthbuf = self.recvall(4)
        if lengthbuf is not None:
            length, = struct.unpack('!I', lengthbuf)
            return self.recvall(length)
        else:
            return None

    def recvall(self, count):
        buf = b''
        while count:
            newbuf = self.socket.recv(count)
            if not newbuf: return None
            buf += newbuf
            count -= len(newbuf)
        return buf

    def __handleIncomingLines(self):
        self.socket.settimeout(1.0)
        buff = b""# While running flag is set
        while self.running is True:
            try:
                if self.withLengthPrefix:
                    msg = self.recvWithLengthPrefix()# self.socket.recv(4096)
                else:
                    msg = self.socket.recv(1024)
                if msg is not None and len(msg) > 0:
                    buff += msg
                    index = buff.find(b"\r\n")
                    while index != -1:
                        msg = buff[:index]
                        for ih in self.incomingHandlers:
                            ih(msg, self)
                        if len(self.incomingHandlers) < 1:
                            if self.loggera and DEBUG:
                                self.logger("%s >>  %s" % (self.TCP_IP, msg))
                        buff = buff[index+2:]
                        index = buff.find(b"\r\n")
                else:
                    if self.logger and DEBUG:
                        self.logger("message to short, treat this as a disconnect")
                        # Remote peer disconnected
                        self.logger("Detected remote disconnect")
                    # Reset running flag such that this function
                    # will stop running
                    self.running = False
                    self.connected = False
                    # Do autoReconnect stuff
                    if self.autoReconnect: self.__reconnect()
            # No data yet
            except socket.timeout:
                continue
                # print("Timeout")
            # Catch other errors
            except socket.error as err:
                if isinstance(err.args, tuple):
                    # Broken Pipe error
                    if err.errno == 32:
                        if self.logger and DEBUG:
                            # Remote peer disconnected
                            self.logger("Detected remote disconnect")
                        # Reset running flag such that this function
                        # will stop running
                        self.running = False
                        self.connected = False
                        # Do autoReconnect stuff
                        if self.autoReconnect: self.__reconnect()
                    else:
                        if self.logger: self.logger("errno is %s" % str(err))
                        pass
                else:
                    if self.logger: self.logger("Socket Error: %s" % str(err))
        self.socket.close()
        if self.logger and DEBUG:
            self.logger("Connection to %s closed" % self.TCP_IP)

    def __handleIncoming(self):
        """
        Call to handle all incoming tcp connections.

        This function handles all socket connections, opens instances of
        clienthandlers and starts/stops their threads.
        """
        self.socket.settimeout(0.5)
        # While running flag is set
        while self.running is True:
            try:
                if self.withLengthPrefix:
                    msg = self.recvWithLengthPrefix()# self.socket.recv(4096)
                else:
                    msg = self.socket.recv(1024)
                if msg is not None and len(msg) > 0:
                    for ih in self.incomingHandlers:
                        ih(msg, self)

                    if len(self.incomingHandlers) < 1:
                        if self.logger and DEBUG:
                            self.logger("%s >>  %s" % (self.TCP_IP, msg))
                else:
                    if self.logger and DEBUG:
                        self.logger("message to short, treat this as a disconnect")
                        # Remote peer disconnected
                        self.logger("Detected remote disconnect")
                    # Reset running flag such that this function
                    # will stop running
                    self.running = False
                    self.connected = False
                    # Do autoReconnect stuff
                    if self.autoReconnect: self.__reconnect()
            # No data yet
            except socket.timeout:
                continue
                # print("Timeout")
            # Catch other errors
            except socket.error as err:
                if isinstance(err.args, tuple):
                    # Broken Pipe error
                    if err.errno == 32:
                        if self.logger and DEBUG:
                            # Remote peer disconnected
                            self.logger("Detected remote disconnect")
                        # Reset running flag such that this function
                        # will stop running
                        self.running = False
                        self.connected = False
                        # Do autoReconnect stuff
                        if self.autoReconnect: self.__reconnect()
                    else:
                        if self.logger: self.logger("errno is %s" % str(err))
                        pass
                else:
                    if self.logger: self.logger("Socket Error: %s" % str(err))
        self.socket.close()
        if self.logger and DEBUG:
            self.logger("Connection to %s closed" % self.TCP_IP)
