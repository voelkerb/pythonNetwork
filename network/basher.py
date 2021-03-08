import sys
import threading
import os
import subprocess
import time
import signal

class Basher():
    """
    Class to execute any command given as a subprocess in a new thread.

    You can wait for execution to finish or execute in the background and check
    the output frequently.
    """

    # Init function
    def __init__(self, command, lineCb=None, echo=False, waittime=1.0):
        """
        Init the Basher
        
        NOTE + TODO: CODE INJECTION is currently possible using Basher!

        :param command: The command to execute in string format.
        :type  command: str
        :param lineCB:  An optional callback which is called for each line output of 
                        the command.
        :type  lineCB:  function(str, Basher), default: ``None``
        :param echo:    If output should be echoed to standard out
        :type  echo:    bool, default: ``False``
        :param waittime:    Time to wait for execution to finish.
                            This only works if :func:`run<terminal.basher.Basher.run> is called with ``wait=True``
        :type  waittime:    float, default: 1.0 
        """
        self.command = command
        self.lineCb = lineCb
        self.output = []
        self.echo = echo
        self.waittime = waittime
        self.startTime = None
        self.__process = None
        self.running = False

    def run(self, wait=True):
        """
        Run the specified command.

        :param wait: If we shoul wait for execution to finish.
        :type  wait: bool, default: True

        :return: List of output lines. 
        :rtype:  list(str)
        """
        self.__process = subprocess.Popen(self.command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
        self.__thread = threading.Thread(target=self.__output_reader)
        self.__thread2 = threading.Thread(target=self.__error_reader)
        self.__thread.daemon = True
        self.__thread2.daemon = True
        self.__thread.start()
        self.__thread2.start()
        self.startTime = time.time()
        self.running=True
        if wait:
            while self.running and time.time()-self.startTime < self.waittime:
                time.sleep(0.01)
            self.stop()
        return self.output

    def stop(self):
        """Stop the execution of the command."""
        self.__process.terminate()
        self.__process.send_signal(signal.SIGTERM)
        # self.__thread.join()
        self.running=False

    def __output_reader(self):
        """Read output in thread."""
        for plain_line in iter(self.__process.stdout.readline, b''):
            line = plain_line.decode('utf-8')
            self.output.append(line)
            if self.echo: print('#BASHER: {0}'.format(line), end='')
            if self.lineCb is not None: self.lineCb(line, self)
        self.running=False

    def __error_reader(self):
        """Read error output in thread."""
        for plain_line in iter(self.__process.stderr.readline, b''):
            line = plain_line.decode('utf-8')
            self.output.append(line)
            if self.echo: print('#BASHER: {0}'.format(line), end='')
            if self.lineCb is not None: self.lineCb(line, self)

