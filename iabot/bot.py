# Copyright Alex Tomkins 2010
#
import libxml2
import urllib
import random

import logging
import time
import csv
import os

from datetime import datetime

from pyxmpp.all import JID, Iq, Presence, Message, StreamError
from pyxmpp.jabber.client import JabberClient
from pyxmpp.jabber.muc import MucRoomManager, MucRoomHandler
from pyxmpp.interfaces import *
from pyxmpp.streambase import stanza_factory
from pyxmpp import xmlextra

from iabot.game import IAGameHandler, IAGameListener
from iabot.auth import IALogin
from iabot.jabber.handlers import MessageHandler, GameHandler
from iabot.jabber.party import ShazbotParty
from iabot.jabber.stats import StatsThread
from iabot.xmpp.clientstream import ClientStreamAsyncore


class IAJabberBot(JabberClient):
    def __init__(self, conf):
        # Various config file bits we'll need
        jid_node = conf.get('login', 'nick')
        jid_domain = conf.get('jabber', 'domain')
        jabber_server = conf.get('jabber', 'server')
        jabber_port = conf.getint('jabber', 'port')

        # Game config
        game_product = conf.getint('game', 'productid')
        game_instance = conf.getint('game', 'instanceid')
        game_maplist = conf.get('game', 'maplist')
        game_maprotation = conf.get('game', 'maprotation')
        game_port = conf.getint('game', 'port')
        game_mode = conf.get('game', 'mode')
        game_timelimit = conf.getint('game', 'timelimit')
        game_scorelimit = conf.getint('game', 'scorelimit')
        game_autostart = conf.getboolean('game', 'autostart')
        game_tournament = conf.getboolean('game', 'tournament')
        game_lt = conf.getboolean('game', 'lt')
        game_grenades = conf.getboolean('game', 'grenades')

        # Listener options
        listen_pid = conf.getint('listener', 'pid')
        listen_tcpip = conf.getboolean('listener', 'tcpip')
        listen_ip = conf.get('listener', 'ip')
        listen_port = conf.getint('listener', 'port')

        # Stats config
        stats_enabled = conf.getboolean('stats', 'enabled')
        stats_urls = conf.get('stats', 'urls')
        stats_retry = conf.getint('stats', 'retry')
        stats_db = conf.get('stats', 'db')

        # Login config
        username = conf.get('login', 'username')
        password = conf.get('login', 'password')
        nickname = conf.get('login', 'nick')
        login_cache = conf.get('login', 'cache')
        browser_agent = conf.get('browser', 'agent')
        homepage_url = conf.get('browser', 'homepage')
        login_url = conf.get('browser', 'login')

        # Party config
        self.party_allowinvites = conf.getboolean('party', 'allowinvites')
        self.party_maxusers = conf.getint('party', 'maxusers')
        self.party_membersonly = conf.getboolean('party', 'membersonly')
        self.party_autoload = conf.getboolean('party', 'autoload')
        self.party_domain = conf.get('jabber', 'parties')
        self.party_gamesdomain = conf.get('jabber', 'games')
        self.party_gamename = conf.get('jabber', 'gamename')

        party_admins_conf = conf.get('party', 'admins')
        self.party_admins = party_admins_conf.lower().split(' ')

        # Generate us some randomish things we'll be needing
        self.ia_clientresource = u'%s_%d' % (
            ''.join([random.choice('0123456789abcdef') for x in range(32)]), time.time())
        self.ia_partyresource = u'%s%s%d' % (
            nickname, ''.join([random.choice('0123456789abcdef') for x in range(32)]), time.time())

        # Need a ticket with our login details
        ia_login = IALogin(browser_agent, homepage_url, login_url, login_cache)
        ticket = ia_login.login(username, password)

        # Setup the client
        jid = JID(jid_node, jid_domain, self.ia_clientresource)
        JabberClient.__init__(
            self, jid, ticket, server=jabber_server, port=jabber_port, auth_methods=('sasl:PLAIN',),
            keepalive=10)
        self.stream_class = ClientStreamAsyncore

        # games JID
        self.game_jid = JID(u'%s/game' % unicode(self.jid))
        self.gamelist_jid = JID(
            u'%s@%s/%s' % (jid_node, self.party_gamesdomain, self.party_gamename))

        # add the separate components
        self.interface_providers = [
            GameHandler(self),
            MessageHandler(self),
        ]

        # Game handler deals with the game messages and game status
        self.game_handler = IAGameHandler(self.message_from_shazbot)

        # Register maps and map rotation with the handler
        maps = csv.reader(open(game_maplist))
        for i in maps:
            self.game_handler.register_map(i[0], i[1], int(i[2]))

        map_rotation = csv.reader(open(game_maprotation))
        for i in map_rotation:
            self.game_handler.add_rotation(i[0], int(i[1]), int(i[2]))

        # Start up the stats thread if enabled, register with the game handler
        if stats_enabled:
            stats_urllist = stats_urls.split(' ')
            self.stats_thread = StatsThread(stats_db, stats_urllist, stats_retry)
            self.stats_thread.start()
        else:
            self.stats_thread = None

        self.game_handler.stats_thread = self.stats_thread

        # Other game settings
        self.game_handler.port = game_port
        self.game_handler.login = nickname
        self.game_handler.mode_name = game_mode
        self.game_handler.timelimit = game_timelimit
        self.game_handler.scorelimit = game_scorelimit
        self.game_handler.autostart = game_autostart
        self.game_handler.tournament = game_tournament
        self.game_handler.lt = game_lt
        self.game_handler.grenades = game_grenades

        # Game listener accepts connections for the game handler
        self.game_listener = IAGameListener(
            game_handler=self.game_handler, product=game_product, instance=game_instance)

        if listen_tcpip:
            self.game_listener.setup_tcpip((listen_ip, listen_port))
        else:
            # Auto detect pid if -1 is given, only useful to specify if game runs under another uid
            if listen_pid == -1:
                self.game_listener.setup_unix()
            else:
                self.game_listener.setup_unix(listen_pid)

    def stream_state_changed(self, state, arg):
        print "*** State changed: %s %r ***" % (state, arg)

    def print_roster_item(self, item):
        if item.name:
            name = item.name
        else:
            name = u""
        print '%s "%s" subscription=%s groups=%s' % (
            unicode(item.jid), name, item.subscription, u",".join(item.groups))

    def roster_updated(self, item=None):
        if not item:
            print u"My roster:"
            for item in self.roster.get_items():
                self.print_roster_item(item)
            return
        print u"Roster item updated:"
        self.print_roster_item(item)

    def session_started(self):
        JabberClient.session_started(self)

        self.room_manager = MucRoomManager(self.stream)
        self.room_manager.set_handlers()

        self.ia_party = ShazbotParty(
            bot=self, game_handler=self.game_handler, game_jid=self.game_jid,
            gamelist_jid=self.gamelist_jid, bot_nick=self.jid.node, autoload=self.party_autoload,
            allow_invites=self.party_allowinvites, size_limit=self.party_maxusers)
        self.ia_party.commands.admins = self.party_admins
        room_id = JID(self.ia_partyresource, self.party_domain)
        self.ia_shazbotjid = room_id

        new_party = self.room_manager.join(room_id, self.jid.node, self.ia_party)
        new_party.request_configuration_form()

    # Iq response goes directly to the game
    def game_iq_success(self, stanza):
        self.message_to_shazbot(stanza)

    # Iq response goes directly to the game
    def game_iq_error(self, stanza):
        self.message_to_shazbot(stanza)

    # Outgoing messages to shazbots
    def message_to_shazbot(self, stanza):
        def clean_node(node):
            node.setNs(None)
            for i in xmlextra.xml_node_iter(node.children):
                clean_node(i)

        # Simplify the to JID
        if stanza.get_to_jid() == self.game_jid:
            stanza.set_to(u'game')

        # This cleans up all the extra junk nsdefs
        clean_node(stanza.xmlnode)
        stanza.xmlnode.removeNsDef(None)
        s = xmlextra.safe_serialize(stanza.xmlnode)

        self.game_handler.send_badfood(s)

    # Incoming messages from shazbots
    def message_from_shazbot(self, data):
        doc = libxml2.parseDoc(data)
        node = doc.getRootElement()

        # Change the from to the full JID
        stanza = stanza_factory(node)
        stanza.set_from(self.game_jid)

        stream = self.get_stream()

        # Have to register Iq stanzas or we'll lose the reply
        if stanza.stanza_type == 'iq':
            if stanza.get_type() in ('get', 'set'):
                stream.set_response_handlers(stanza, self.game_iq_success, self.game_iq_error)

        stream.send(stanza)
        doc.freeDoc()

    # Extending idle with whatever extra bits we need to do
    def idle(self):
        JabberClient.idle(self)

        if self.game_handler.countdown:
            self.game_handler.countdown_step()
