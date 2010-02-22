from pyxmpp.clientstream import ClientStream
from pyxmpp.exceptions import ClientStreamError
from pyxmpp.exceptions import FatalStreamError
from dispatcher import StreamDispatcher
import logging


class ClientStreamAsyncore(ClientStream):
    def __init__(self, jid, password=None, server=None, port=None,
                 auth_methods=("sasl:DIGEST-MD5",), tls_settings=None, keepalive=0, owner=None):
        ClientStream.__init__(
            self, jid=jid, password=password, server=server, port=port, auth_methods=auth_methods,
            tls_settings=tls_settings, keepalive=keepalive, owner=owner)
        self.__logger = logging.getLogger("iabot.xmpp.ClientStreamAsyncore")

    def _write_raw(self, data):
        logging.getLogger("pyxmpp.Stream.out").debug("OUT: %r", data)
        self.dispatcher.buffer += data
        # try:
        #    self.socket.send(data)
        # except (IOError,OSError,socket.error),e:
        #    raise FatalStreamError("IO Error: "+str(e))

    def _connect(self, server=None, port=None):
        if not self.my_jid.node or not self.my_jid.resource:
            raise ClientStreamError, "Client JID must have username and resource"
        if not server:
            server = self.server
        if not port:
            port = self.port
        if server:
            self.__logger.debug("server: %r", (server,))
            service = None
        else:
            service = "xmpp-client"
        if port is None:
            port = 5222
        if server is None:
            server = self.my_jid.domain
        self.me = self.my_jid

        # Having to deal with a service would be painful, and isn't needed
        if service:
            raise ClientStreamError, "IABot cannot deal with SRV record lookups"

        if self.my_jid.domain is None:
            to = str(addr)
        else:
            to = self.my_jid.domain

        self.dispatcher = StreamDispatcher(self, server, port)

        self._connect_socket(sock=True, to=to)
        # self.initiator=1
        # self._send_stream_start()

    # We need support for custom from stanzas
    def fix_out_stanza(self, stanza):
        if not stanza.get_from():
            stanza.set_from(self.my_jid)
