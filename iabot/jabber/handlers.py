from pyxmpp.interfaces import IMessageHandlersProvider, IIqHandlersProvider
try:
    from zope.interface import implements
except ImportError:
    from pyxmpp.interface_micro_impl import implements
from pyxmpp.all import Message
import re


class MessageHandler(object):
    implements(IMessageHandlersProvider)

    def __init__(self, client):
        self.client = client

    # Deal with all private messages
    def get_message_handlers(self):
        return [
            ('normal', self.message),
        ]

    def message(self, stanza):
        subject = stanza.get_subject()
        body = stanza.get_body()
        t = stanza.get_type()
        print u'Message from %s received.' % (unicode(stanza.get_from(),)),

        if t:
            if t == 'chat':
                if not body:
                    command_message = stanza.xpath_eval("ns:command")

                    if command_message:
                        command = stanza.xpath_eval("ns:command/ns:command")

                        if command:
                            command_text = command[0].getContent()

                            if command_text == 'requestLobby':
                                self.client.ia_party.show_state()
                                return True
                            elif command_text == 'requestSettings':
                                self.client.ia_party.show_settings()
                                return True
                    else:
                        print "no command"

                else:
                    msg_from = stanza.get_from()

                    if not self.client.ia_party.commands.is_admin(msg_from.node):
                        return

                    msg = stanza.get_body()
                    bang_re = re.compile('^!(\w+)( .*)?$')
                    bang_cmd = bang_re.match(msg)

                    if not bang_cmd:
                        return

                    (command, args) = bang_cmd.groups()
                    command = command.lower()

                    if args:
                        args = args.strip().rstrip()

                    bang_command = self.client.ia_party.commands.get_command(command)

                    if bang_command:
                        result = bang_command(stanza.get_from(), args)

                        if result:
                            # Have to insert a bit of XML into the body, grrr
                            m = Message(to_jid=stanza.get_from(), stanza_type='headline')
                            body_node = m.add_new_content(None, 'body')
                            body_node.setContent(result)
                            party_node = body_node.newChild(
                                None, 'party', self.client.ia_partyresource)

                            stream = self.client.stream
                            stream.send(m)

                        return True


class GameHandler(object):
    implements(IIqHandlersProvider)

    def __init__(self, client):
        self.client = client

    def get_iq_get_handlers(self):
        return []

    def get_iq_set_handlers(self):
        return [
            ('query', 'garagegames:connect', self.gg_connect),
        ]

    def gg_connect(self, iq):
        # result_iq = iq.make_result_response()

        # Any Iq requests to the game we don't deal with
        if iq.get_to_jid() == self.client.game_jid:
            self.client.message_to_shazbot(iq)

        return True
        # return result_iq
