import socket
import os
import binascii
from struct import unpack, pack
import time
import asyncore
import asynchat
import os
from struct import unpack, pack
from pyxmpp.stanza import Stanza
from pyxmpp.iq import Iq
from pyxmpp.message import Message
from pyxmpp.presence import Presence
from pyxmpp import xmlextra
from pyxmpp.all import JID
from pyxmpp.streambase import stanza_factory
import libxml2
import time
from iabot.jabber.extras import clean_node


class GameInProgress(Exception):
    pass


class GameNotRunning(Exception):
    pass


LEGIONS_GAMETYPES = {
    'ctf':          {'teams': 2, 'mode': 'CTF'},
    'tdm':          {'teams': 2, 'mode': 'Deathmatch'},
    'deathmatch':   {'teams': 0, 'mode': 'Deathmatch'},
    'hunters':      {'teams': 0, 'mode': 'Hunters'},
    'rabbit':       {'teams': 0, 'mode': 'Rabbit'},
}


class IAGameHandler(object):
    def __init__(self, outgoing_msg):
        self.conn = None
        self.outgoing_msg = outgoing_msg
        self.running = False
        self.playing = False
        self.maps = {}
        self.map_rotation = []
        self.rotation_cur = -1
        self.player_count = 1
        self.countdown = None
        self.countdown_nextshow = 0
        self.party_handler = None
        self.gamelist_jid = None
        self.stats_thread = None

        # Server settings
        self.port = None
        self.login = None

        # Game settings
        self.level = None
        self.level_id = None
        self.mission = None
        self.mode = None
        self.mode_name = None
        self.timelimit = 1
        self.scorelimit = 10
        self.teams = 2
        self.autostart = False
        self.lt = False
        self.grenades = False
        self.tournament = False

    def connected(self, connection):
        self.conn = connection
        print "now connected to", connection

        self.party_handler.server_connected()

        welcome_msg = pack('4i', 0, 0, 0, 0)
        self.send_badfood(welcome_msg, msg_type=1)

    def disconnected(self):
        print "Disconnected"
        self.running = False
        self.playing = False
        self.countdown = None
        self.party_handler.server_disconnected()

    def set_level(self, level_name):
        level_name = level_name.lower()

        if self.playing:
            # No changing whilst running
            raise GameInProgress

        if level_name not in self.maps:
            # Not valid, so return the current one
            return self.level

        self.level = self.maps[level_name]['map']
        self.level_id = self.maps[level_name]['id']
        self.mission = self.maps[level_name]['mission']

        self.party_handler.set_level(self.level, self.level_id)

        return self.level

    def set_mode(self, mode):
        mode = mode.lower()

        if self.playing:
            # No changing whilst running
            raise GameInProgress

        if mode in LEGIONS_GAMETYPES:
            self.mode_name = mode
            self.mode = LEGIONS_GAMETYPES[mode]['mode']
            self.teams = LEGIONS_GAMETYPES[mode]['teams']

        self.party_handler.set_mode(self.mode, self.teams)
        return self.mode

    def set_autostart(self, autostart):
        self.autostart = autostart

        if not autostart:
            if self.countdown > 0:
                self.countdown_cancel = True

        return autostart

    def set_lt(self, lt):
        self.lt = lt
        return lt

    def set_tournament(self, tournament):
        self.tournament = tournament
        return tournament

    def set_timelimit(self, new_limit):
        if self.playing:
            # No changing whilst running
            raise GameInProgress

        self.timelimit = new_limit
        self.party_handler.set_timelimit(new_limit)
        return new_limit

    def set_scorelimit(self, new_limit):
        if self.playing:
            # No changing whilst running
            raise GameInProgress

        self.scorelimit = new_limit
        self.party_handler.set_scorelimit(new_limit)
        return new_limit

    def set_teams(self, teams):
        if self.playing:
            # No changing whilst running
            raise GameInProgress

        self.teams = teams
        self.party_handler.set_teams(teams)
        return teams

    def update_playercount(self, players):
        self.player_count = players

    def countdown_start(self):
        countdown_time = 45
        self.party_handler.countdown_notice(countdown_time)

        self.countdown = time.time()+countdown_time
        self.countdown_nextshow = ((countdown_time-1)/10)*10

    def countdown_stop(self):
        if self.countdown:
            self.countdown = None
            return True
        else:
            return False

    def countdown_step(self):
        # Just incase something strange happens
        if not self.countdown:
            return

        time_now = time.time()

        # Start!
        if time_now >= self.countdown:
            self.countdown = None
            self.party_handler.countdown_notice(0)
            self.start_game()
            return

        time_left = self.countdown-time_now

        # Time for another tick show
        if time_left <= self.countdown_nextshow:
            self.party_handler.countdown_notice(self.countdown_nextshow)
            self.countdown_nextshow = ((self.countdown_nextshow-1)/10)*10

    def change_level(self, map_name):
        map_name = map_name.lower()

        if self.playing:
            # No changing whilst running
            return False

        if map_name not in self.maps:
            # Not valid, so return the current one
            return self.level

        self.level = self.maps[map_name]['map']
        self.mission = self.maps[map_name]['mission']

        self.party_handler.set_level(self.level, 0)
        return self.level

    def register_map(self, map_name, mission_name, level_id):
        self.maps[map_name.lower()] = {'map': map_name, 'mission': mission_name, 'id': level_id}

        if not self.level:
            print "%s is now first map" % map_name
            self.level = map_name
            self.mission = mission_name
            self.level_id = level_id

    def add_rotation(self, map_name, min_limit, max_limit):
        self.map_rotation.append((map_name, min_limit, max_limit))

    def next_rotation(self):
        self.rotation_cur += 1

        # Loop back to start
        if self.rotation_cur >= len(self.map_rotation):
            self.rotation_cur = 0

        (map_name, min_limit, max_limit) = self.map_rotation[self.rotation_cur]
        num_players = self.player_count

        if num_players < min_limit:
            # Too few players, find another
            return self.next_rotation()

        elif max_limit and num_players > max_limit:
            # Too many players, find another
            return self.next_rotation()

        else:
            # Juuust right
            return map_name

    def send_badfood(self, data='', msg_type=0):
        # 0x0BADF00D
        badfood = pack('4B', 0x0D, 0xF0, 0xAD, 0x0B)

        # Message type, 4 bytes
        badfood += pack('i', msg_type)

        # Message length, 4 bytes
        badfood += pack('i', len(data))

        # Sometimes the payload can be nothing (why?!)
        if data:
            badfood += data

        if msg_type == 0:
            print '    >>> MSG(%d):' % msg_type, data
        else:
            print '    >>> MSG(%d):' % msg_type, ' '.join([binascii.hexlify(x) for x in data])

        self.conn.push(badfood)

    def eat_badfood(self, data='', msg_type=0):
        if msg_type == 0:
            print '<<< MSG(%d):' % msg_type, data
        else:
            print '<<< MSG(%d):' % msg_type, ' '.join([binascii.hexlify(x) for x in data])

        if msg_type == 1:
            self.send_badfood(msg_type=1)

        elif msg_type == 0:
            doc = libxml2.parseDoc(data)
            node = doc.getRootElement()

            stanza = stanza_factory(node)

            if stanza.stanza_type == 'iq':
                self.process_iq(stanza, data)
            elif stanza.stanza_type == 'message':
                self.process_message(stanza, data)
            elif stanza.stanza_type == 'presence':
                self.process_presence(stanza, data)
            else:
                self.process_stanza(stanza, data)

            doc.freeDoc()

    def process_stanza(self, stanza, data):
        print stanza

    def process_presence(self, presence, data):
        self.outgoing_msg(data)

    def process_message(self, message, data):
        if message.get_to() != u'browser':
            return

        data_nodes = message.xpath_eval('//ggc:data', {'ggc': 'garagegames:connect'})

        if not data_nodes:
            return

        data_node = data_nodes[0]

        browser_message = data_node.content.strip().rstrip()
        (message_id, message_cmd, status_data) = browser_message.split(',', 2)

        if ',' in status_data:
            status, data = status_data.split(',', 1)
        else:
            status = status_data
            data = None

        if message_cmd == 'GameReady':
            # Game alive, start it
            self.send_command('game.init', {
                'dedicated': 'true',
            })
            self.party_handler.server_loading()

        elif message_cmd == 'GameIdle':
            # Game needs to initiate
            self.send_command('game.host.init', {
                'serverName': 'Legions Party',
                'jid': self.gamelist_jid,
            })

        elif message_cmd == 'DomainIdle':
            # First time the server is ready to go
            self.running = True

            self.set_timelimit(self.timelimit)
            self.set_scorelimit(self.scorelimit)
            self.set_mode(self.mode_name)
            self.set_level(self.level)
            # self.set_teams(self.teams)

            if self.autostart:
                next_map = self.next_rotation()
                self.set_level(next_map)
                self.party_handler.server_ready()
                self.countdown_start()
                # self.start_game()
            else:
                self.party_handler.server_ready()

        elif message_cmd == 'HostRegistrationComplete':
            # Lobby registered with the game list
            self.party_handler.server_registered()

        elif message_cmd == 'SessionScores':
            # Game scores, but only if enabled
            if self.stats_thread:
                stats_nodes = message.xpath_eval('//ggc:data/ls:stats/*[1]', {
                    'ggc': 'garagegames:connect',
                    'ls': 'legions:stats',
                })

                if stats_nodes:
                    stats = stats_nodes[0]
                    clean_node(stats)
                    xml_data = stats.serialize()
                    self.stats_thread.add_stats(xml_data)

        elif message_cmd == 'SessionEnded':
            # Map ended, so we need to acknowledge it
            self.send_command('game.host.ackEnd', {
            })

        elif message_cmd == 'SessionKilled':
            # Now that map has really ended and we'll be in an empty state
            self.playing = False

            if self.autostart:
                next_map = self.next_rotation()
                self.set_level(next_map)
                self.countdown_start()

    def start_game(self):
        if self.playing:
            # No changing whilst running
            raise GameInProgress

        self.send_command('prefs.game.setScoreLimit', {
            'points': str(self.scorelimit),
        })
        self.send_command('prefs.game.setTimeLimit', {
            'minutes': str(self.timelimit),
        })
        self.send_command('prefs.game.setTeamCount', {
            'teams': str(self.teams),
        })
        self.send_command('prefs.game.setTournamentMode', {
            'enabled': self.tournament,
        })
        self.send_command('prefs.game.SetLTEnabled', {
            'enabled': self.lt,
        })
        self.send_command('prefs.game.SetGrenadesEnabled', {
            'enabled': self.grenades,
        })
        self.playing = True
        mission_name = self.mission
        self.send_command('game.host.start', {
            'mode': self.mode,
            'level': mission_name,
        })
        return True

    def stop_game(self):
        if self.playing:
            self.send_command('game.host.over', {
            })
            return True
        else:
            return False

    def send_command(self, command, args):
        init_iq = Iq(stanza_type='set', to_jid=u'game', from_jid=u'browser')
        query_node = init_iq.new_query('garagegames:connect')
        query_node.newChild(None, 'command', command)
        args_node = query_node.newChild(None, 'args', None)

        for i in args:
            if isinstance(args[i], bool):
                arg_node = args_node.newChild(None, i, str(int(args[i])))
                arg_node.setProp('type', 'boolean')
            else:
                args_node.newChild(None, i, args[i])

        self.send_badfood(init_iq.serialize())

    def process_iq(self, iq, data):
        to_jid = iq.get_to()

        if to_jid == u'game':
            # Not sure why messages to the game come to us, but we just send them back
            self.send_badfood(data)

        elif to_jid == u'plugin':
            # We are the browser, so process the message

            # Not bothered with replies
            if iq.get_type() not in [u'get', u'set']:
                return

            query_node = iq.get_query()
            xmlextra.replace_ns(query_node, query_node.ns(), None)

            xpc = xmlextra.common_doc.xpathNewContext()
            xpc.setContextNode(query_node)

            command_node = xpc.xpathEval("command/text()")
            command = None

            if command_node:
                command = command_node[0].content

            arg_nodes = xpc.xpathEval("args/*")

            args = {}

            if arg_nodes:
                for i in arg_nodes:
                    args[i.name] = i.content

            xpc.xpathFreeContext()

            if not command:
                return

            result_iq = iq.make_result_response()

            print command
            if command == 'variable.get':
                if 'name' in args:
                    get_var = args['name']

                    query_node = result_iq.set_new_content('garagegames:connect', 'query')
                    query_node.setProp('code', '0')
                    value_node = query_node.newChild(None, 'value', None)

                    if get_var == 'plugin.xmpp.domain':
                        value_node.setContent('instantaction.com')
                    elif get_var == 'system.user.id':
                        value_node.setContent('1234')
                    elif get_var == 'system.user.login':
                        value_node.setContent(self.login)
                    elif get_var == 'game.networking.port':
                        value_node.setContent(str(self.port))
                    elif get_var == 'game.match.id':
                        value_node.setContent('%s19884641' % self.login)

            self.send_badfood(result_iq.serialize())

        elif to_jid == u'browser':
            pass

        else:
            self.outgoing_msg(data)


class IAGameConnection(asynchat.async_chat):
    ac_in_buffer_size = 65536
    ac_out_buffer_size = 65536

    def __init__(self, sock, listener, game_handler):
        asynchat.async_chat.__init__(self, sock)

        self.listener = listener
        self.set_terminator(4)
        self.data = ''
        self.header = False
        self.message_type = None
        self.message_length = None
        self.handler = game_handler
        self.handler.connected(self)

    def push(self, data):
        self.producer_fifo.push(asynchat.simple_producer(data, buffer_size=self.ac_out_buffer_size))
        self.initiate_send()

    def collect_incoming_data(self, data):
        self.data += data

    def found_terminator(self):
        # 0x0BADF00D
        if not self.header:
            if list(self.data) != [chr(x) for x in [0x0D, 0xF0, 0xAD, 0x0B]]:
                raise ValueError
            self.data = ''
            self.header = True
            self.set_terminator(4)

        # Message type, 4 bytes
        elif self.message_type is None:
            (self.message_type,) = unpack('i', self.data)
            self.data = ''
            self.set_terminator(4)

        # Message length, 4 bytes
        elif self.message_length is None:
            (self.message_length,) = unpack('i', self.data)
            self.data = ''

            # Sometimes the payload can be nothing (why?!)
            if self.message_length == 0:
                self.handler.eat_badfood('', self.message_type)

                self.header = False
                self.message_type = None
                self.message_length = None
                self.set_terminator(4)
            else:
                self.set_terminator(self.message_length)

        # Message payload
        else:
            self.handler.eat_badfood(self.data, self.message_type)

            self.data = ''
            self.header = False
            self.message_type = None
            self.message_length = None
            self.set_terminator(4)

    def handle_close(self):
        self.close()

        # Inform the party
        self.handler.disconnected()

        # Allow server to reconnect
        self.listener.game_active = False


class IAGameListener(asynchat.async_chat):
    def __init__(self, game_handler, product, instance):
        asynchat.async_chat.__init__(self)
        self.game_active = False
        self.game_handler = game_handler
        self.product = product
        self.instance = instance
        self.conf_tcpip = None
        self.conf_unix = None

    # Setup for a UNIX socket
    def setup_unix(self, uid=None):
        self.conf_tcpip = None
        self.conf_unix = uid

    # Setup for a TCP/IP socket
    def setup_tcpip(self, ipport):
        self.conf_tcpip = ipport

    # Listen on a UNIX socket, the default IA game way
    def listen_unix(self, uid):
        filename = '/tmp/%.8d.IAPlayer.%d.%d' % (uid, self.product, self.instance)

        try:
            os.remove(filename)
        except OSError:
            pass

        self.create_socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.bind(filename)
        self.listen(1)
        print "Listening on %s" % filename

    # Listen on a TCP/IP socket, useful for running the game on other machines
    def listen_tcpip(self):
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(self.conf_tcpip)
        self.listen(1)
        print "Listening on %s, port %d" % self.conf_tcpip

    # Listen with the info given earlier
    def listen_for_game(self):
        if self.conf_tcpip:
            self.listen_tcpip()
        else:
            if self.conf_unix:
                self.listen_unix(self.conf_unix)
            else:
                self.listen_unix(os.getuid())

    # Accept connection - but only accept one!
    def handle_accept(self):
        conn, addr = self.accept()
        print "Accepting conn"

        if not self.game_active:
            self.game_active = True
            IAGameConnection(conn, self, self.game_handler)

    def handle_connect(self):
        pass
