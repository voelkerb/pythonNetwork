# python TCP servers and clients 

Easy TCP client and server modules for python.


# TCP Server

Create a TCP server instance at ```localhost``` port ```2000``` using:
```python
net = NetworkServer(port=2000, ip="127.0.0.1", requestHandler=request)
net.startServer()
```

Optionally, you can pass a ```requestHandler``` function:

```python
def request(addr, msg, clientHandler):
    try:
        line = msg.decode("utf-8").replace("\r", "").replace("\n", "")
    except:
        line = str(msg)
    print(str(addr) + ": " + str(line))
    # Simply echo back what was received
    clientHandler.sendMsg(str(line))
```
You can also broadcast a message to all connected clients using:

```python
net.broadcastMessage("Hello All!")
```

For a direct example, see TCPServer.py 
```bash
python3 TCPServer.py --ip "0.0.0.0" --port 2000 
```


# TCP Client

Create a TCP client instance and connect to a server at ```192.168.0.13``` port ```2000``` using:
```python
client = NetworkClient(port=2000, ip="192.168.0.13", incomingHandler=inputFromServer, withLengthPrefix=False, lines=True)
client.connect()
```

Optionally, you can pass a ```inputFromServer``` function:

```python
def inputFromServer(msg, client):
    print("\r<" + client.TCP_IP + ": ", end="")
    print(msg.decode("utf-8"))
    print("\n>" + str(client.TCP_IP) + "$ ", end="")
```
You can also send a message to the server using:

```python
client.sendMsg("Hello from client")
```

For a direct example, see TCPServer.py 
```bash
python3 TCPClient.py --ip "192.168.0.13" --port 2000 
```


# mDNS

Start by creating an mDNS Instance
```python
mdns = mDNS()
```

You can now resolve mDNS names 
```python
possibleHosts = ["test" + str(i) for i in range(10)]
resolvedHosts = mdns.resolveNames(hosts)
```

You can also search for announced services (e.g. the ```_elec``` service of type ```_tcp```)
```python
devices = mdns.searchForService("_elec", "_tcp")
```
The result is a list of tuples, with the mDNS name of the devices and their resolved IP address. 
```
[('smartmeter001.local', '192.168.0.36'), ('powermeter28.local', '192.168.0.114'), ('powermeter20.local', '192.168.0.111'), ('powermeter15.local', '192.168.0.113'), ('powermeter24.local', '192.168.0.115'), ('powermeter21.local', '192.168.0.118'), ('powermeter27.local', '192.168.0.138')]
```

Or announce you own service at e.g. IP ```192.168.0.13``` and port ```2000``` the following way:
```python
mdns.announce("my_mDNS_name", "my_service_name", "my_service_type", "192.168.0.13", 2000)