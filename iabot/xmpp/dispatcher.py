import asyncore
import socket
import time


class StreamDispatcher(asyncore.dispatcher):
    def __init__(self, stream, addr, port):
        asyncore.dispatcher.__init__(self)
        self.stream = stream
        self.buffer = ""

        self.stream.state_change("connecting", (addr, port))

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((addr, port))

    def handle_connect(self):
        self.stream.state_change("connected", self.socket.getpeername())
        self.stream.last_keepalive = time.time()

    def handle_close(self):
        self.close()

    def handle_read(self):
        data = self.recv(8192)
        self.stream.lock.acquire()
        try:
            self.stream._feed_reader(data)
        finally:
            self.stream.lock.release()

    def writable(self):
        return (len(self.buffer) > 0)

    def handle_write(self):
        sent = self.send(self.buffer)
        self.buffer = self.buffer[sent:]
