from pyxmpp.jabber.muc import MucRoomHandler
from pyxmpp.all import JID, Presence, Message, Iq
from pyxmpp.jabber.muccore import MucIq, MucAdminQuery, MucItem
import random
import re
import urllib
from datetime import datetime
from iabot.game import GameInProgress
from iabot.jabber.commands import IAPartyCommands
from iabot.jabber.extras import yes_or_no


LEGIONS_GAMETYPES = ('CTF', 'deathmatch')
LEGIONS_GAMETYPES_DICT = dict([(x.lower(), x) for x in LEGIONS_GAMETYPES])


class ShazbotParty(MucRoomHandler):
    def __init__(self, bot, game_handler, game_jid, gamelist_jid, bot_nick, autoload,
                 allow_invites, size_limit):
        MucRoomHandler.__init__(self)
        self.ia_avatarcache = u''.join([random.choice('0123456789abcdef') for x in range(32)])
        self.game_jid = game_jid
        self.gamelist_jid = gamelist_jid
        self.bot = bot
        self.game_handler = game_handler
        self.commands = IAPartyCommands(self, game=game_handler)
        self.allow_invites = allow_invites
        self.size_limit = size_limit
        self.private = False
        self.config_form = None

        # Lobby state
        self.lobby_started = datetime.utcnow().replace(microsecond=0).isoformat()
        self.lobby_registered = False

        # Lobby settings
        self.bot_nick = bot_nick
        self.autoload = autoload

        # Game state
        self.state = 'lobby'
        self.loaded = False

        # Game settings
        self.level = None
        self.level_id = None
        self.mode = 'CTF'
        self.timelimit = None
        self.scorelimit = None
        self.teams = None
        self.autostart = None

    def message_received(self, user, stanza):
        MucRoomHandler.message_received(self, user, stanza)

        # Messages can come from the party and not a user
        if not user:
            return

        if not self.commands.is_admin(user.nick):
            return

        msg = stanza.get_body()

        if not msg:
            return

        bang_re = re.compile('^!(\w+)( .*)?$')
        bang_cmd = bang_re.match(msg)

        if not bang_cmd:
            return

        (command, args) = bang_cmd.groups()
        command = command.lower()

        if args:
            args = args.strip().rstrip()

        bang_command = self.commands.get_command(command)

        if bang_command:
            result = bang_command(user, args)

            if result:
                self.room_state.send_message(result)

    def countdown_notice(self, seconds):
        if seconds == 0:
            self.room_state.send_message('Starting map.')
        else:
            self.room_state.send_message('Starting next map in %d seconds...' % seconds)

    def configuration_form_received(self, form):
        form['muc#roomconfig_membersonly'].value = self.private
        form['muc#roomconfig_allowinvites'].value = self.allow_invites
        form['muc#roomconfig_maxusers'].value = self.size_limit
        self.config_form = form
        submit_form = form.make_submit(keep_types=True)
        self.room_state.configure_room(submit_form)

    def party_settings(self, **kwargs):
        if 'private' in kwargs:
            self.private = kwargs['private']
            self.config_form['muc#roomconfig_membersonly'].value = self.private

        if 'limit' in kwargs:
            self.size_limit = kwargs['limit']
            self.config_form['muc#roomconfig_maxusers'].value = self.size_limit

        submit_form = self.config_form.make_submit(keep_types=True)
        self.room_state.configure_room(submit_form)
        self.shazbot_update_usercount()
        self.party_refresh()
        self.lobby_update()

    def room_configured(self):
        print "Room Configured"
        MucRoomHandler.room_configured(self)

    def room_created(self, stanza):
        MucRoomHandler.room_created(self, stanza)
        print "************** Room Created"
        # self.room_state.request_configuration_form()

    def user_joined(self, user, stanza):
        MucRoomHandler.user_joined(self, user, stanza)

        print "*** User joined: %s" % user.nick
        stream = self.room_state.manager.stream

        if user.nick == self.bot_nick:
            # Send a basic presence until the game is loaded
            self.show_presence()

            self.game_handler.party_handler = self
            self.game_handler.gamelist_jid = unicode(self.gamelist_jid)

            # CHANGE: game process will be managed by this, eventually
            #         but our socket will always listen whilst this party is here
            # if self.autoload:
            #    self.game_thread.start()
            self.bot.game_listener.listen_for_game()
        else:
            pass

        self.shazbot_update_usercount()

    def kick_user(self, victim):
        kick_iq = MucIq(
            from_jid=self.bot.jid, to_jid=self.room_state.room_jid.bare(), stanza_type='set')
        kick_item = kick_iq.make_kick_request(victim, "You have been kicked.")
        # kick_iq.clear_muc_child()
        # print "one"
        # kick_iq.muc_child = MucAdminQuery(parent=kick_iq.xmlnode)
        # print "one"
        # kick_item = MucItem("none","none",nick=victim,reason="You have been kicked.")
        # print "one"
        # kick_item.xmlnode.unsetProp('affiliation')
        # print "one"
        # kick_iq.muc_child.add_item(kick_item)
        # print "one"
        #
        # print kick_item
        # print kick_item.xmlnode.serialize()
        #
        print kick_item.xmlnode.serialize()
        stream = self.room_state.manager.stream
        stream.send(kick_iq)

    def server_connected(self):
        self.room_state.send_message('Game loading...')

    def server_disconnected(self):
        self.room_state.send_message('Game terminated.')

        self.lobby_registered = False

        # Unregister with the gamelist
        unregister = Presence(
            from_jid=self.game_jid, to_jid=self.gamelist_jid, stanza_type='unavailable')

        self.state = 'choosing_game'
        self.show_presence()
        self.show_state()

    def server_loading(self):
        self.room_state.send_message('DEBUG: Server LOADING.')

        self.state = 'loading'
        self.show_presence()
        self.show_state()

    def server_registered(self):
        self.room_state.send_message('DEBUG: Server REGISTERED.')

        self.lobby_registered = True
        # Not going to work here!
        # self.lobby_update()

    def server_ready(self):
        self.room_state.send_message('DEBUG: Server READY.')

        self.state = 'ready'
        self.lobby_update()
        self.show_presence()
        self.show_state()
        self.show_settings()

    def server_playing(self):
        self.room_state.send_message('DEBUG: Server PLAYING.')

        self.state = 'playing'
        self.show_presence()
        self.show_state()

    def set_level(self, level, level_id):
        self.level = level
        self.level_id = level_id
        self.settings_changed()

    def set_mode(self, mode, teams):
        self.mode = mode
        self.teams = teams

        if mode.lower() not in LEGIONS_GAMETYPES_DICT:
            self.room_state.send_message('Custom game type: %s' % mode)

        self.settings_changed()

    def set_timelimit(self, timelimit):
        self.timelimit = timelimit

        # Inform the party as these can't be displayed
        if timelimit not in [-1, 5, 10, 15, 20, 25, 30, 45, 60]:
            self.room_state.send_message('Custom time limit: %d mins' % timelimit)

        self.settings_changed()

    def set_scorelimit(self, scorelimit):
        # Inform the party as these can't be displayed
        if self.mode == 'CTF':
            if scorelimit not in [-1, 1, 2, 5, 10, 15, 25]:
                self.room_state.send_message('Custom score limit: %d' % scorelimit)
        else:
            # All others follow "deathmatch" scoring rules
            if scorelimit not in [-1, 10, 20, 50, 100]:
                self.room_state.send_message('Custom score limit: %d' % scorelimit)

        self.scorelimit = scorelimit
        self.settings_changed()

    # def set_teams(self, teams):
    #    with self.lock:
    #        self.teams = teams
    #        self.settings_changed()

    def set_state(self, state):
        self.state = state
        self.show_presence()
        self.show_state()

        if state == 'ready':
            self.show_settings()

    def settings_changed(self):
        # Don't update the party unless we're loaded
        if self.state in ['ready', 'playing']:
            self.show_state()
            self.lobby_update()
            self.show_settings()

    # Status updates are shown to the party as a message
    def show_state(self):
        m = Message(to_jid=self.room_state.room_jid.bare(), stanza_type='groupchat')
        query_node = m.add_new_content(None, 'query')
        args_node = query_node.newChild(None, 'args', None)
        args_node.newChild(None, 'state', self.state)
        canhost_node = args_node.newChild(None, 'canHost', 'true')
        canhost_node.setProp('type', 'boolean')
        args_node.newChild(None, 'matchID', '%s19884641' % self.bot_nick)

        if self.state in ['ready', 'playing']:
            args_node.newChild(None, 'game', 'Legions')
            args_node.newChild(None, 'gameLevelId', str(self.level_id))
            args_node.newChild(None, 'gameLevel', self.level)
            args_node.newChild(None, 'gameMode', self.mode)
            args_node.newChild(None, 'jid', unicode(self.gamelist_jid))

        # args_node.newChild(None, 'anonymous', '0')
        maxplayers_node = args_node.newChild(None, 'maxplayers', str(self.size_limit))
        maxplayers_node.setProp('type', 'number')
        args_node.newChild(None, 'partyJID', unicode(self.room_state.room_jid.bare()))
        args_node.newChild(None, 'private', yes_or_no(self.private))
        args_node.newChild(None, 'allowAnon', 'no')
        args_node.newChild(None, 'createdAt', self.lobby_started)

        stream = self.room_state.manager.stream
        stream.send(m)

    # Lobby updates to to the game JID
    def lobby_update(self):
        # Only update if we're registered
        if not self.lobby_registered:
            return

        update_iq = Iq(stanza_type='set', to_jid=self.gamelist_jid)
        query_node = update_iq.new_query('garagegames:connect')
        query_node.newChild(None, 'command', 'lobby.update')
        args_node = query_node.newChild(None, 'args', None)
        args_node.newChild(None, 'state', self.state)
        canhost_node = args_node.newChild(None, 'canHost', 'true')
        canhost_node.setProp('type', 'boolean')

        if self.state in ['ready', 'playing']:
            args_node.newChild(None, 'matchID', '%s19884641' % self.bot_nick)
            args_node.newChild(None, 'game', 'Legions')
            args_node.newChild(None, 'gameLevelId', str(self.level_id))
            args_node.newChild(None, 'gameLevel', self.level)

            if self.game_handler.lt:
                game_mode = u'LT %s' % self.mode
            else:
                game_mode = self.mode

            args_node.newChild(None, 'gameMode', game_mode)
            args_node.newChild(None, 'jid', unicode(self.gamelist_jid))

        maxplayers_node = args_node.newChild(None, 'maxplayers', str(self.size_limit))
        maxplayers_node.setProp('type', 'number')
        args_node.newChild(None, 'partyJID', unicode(self.room_state.room_jid.bare()))
        args_node.newChild(None, 'private', yes_or_no(self.private))
        args_node.newChild(None, 'allowAnon', 'no')
        args_node.newChild(None, 'createdAt', self.lobby_started)
        # args_node.newChild(None, 'dedicatedServer', 'true')

        stream = self.room_state.manager.stream
        stream.send(update_iq)

    # Game settings are displayed to the party as a message
    def show_settings(self):
        m = Message(to_jid=self.room_state.room_jid.bare(), stanza_type='groupchat')
        command_node = m.add_new_content(None, 'command')
        command_node.newChild(None, 'command', 'settings')
        command_node.newChild(None, 'level', str(self.level_id))

        # Custom type if Flash isn't going to know about it
        if self.mode.lower() in LEGIONS_GAMETYPES_DICT:
            command_node.newChild(None, 'mode', LEGIONS_GAMETYPES_DICT[self.mode.lower()])
        else:
            command_node.newChild(None, 'mode', 'deathmatch')

        # Show a specific limit if score can't be displayed
        show_scorelimit = self.scorelimit
        if self.mode == 'CTF':
            if self.scorelimit not in [1, 2, 5, 10, 15, 25]:
                show_scorelimit = 1
        else:
            if self.scorelimit not in [10, 20, 50, 100]:
                show_scorelimit = 100

        scorelimit_node = command_node.newChild(None, 'scorelimit', str(show_scorelimit))
        scorelimit_node.setProp('type', 'number')
        teams_node = command_node.newChild(None, 'teams', str(self.teams))
        teams_node.setProp('type', 'number')

        # Show custom time limits as "unlimited"
        if self.timelimit in [-1, 5, 10, 15, 20, 25, 30, 45, 60]:
            timelimit_node = command_node.newChild(None, 'timelimit', str(self.timelimit))
        else:
            timelimit_node = command_node.newChild(None, 'timelimit', '-1')
        timelimit_node.setProp('type', 'number')

        stream = self.room_state.manager.stream
        stream.send(m)

    # Ask a party to refresh after party settings changes
    def party_refresh(self):
        m = Message(to_jid=self.room_state.room_jid.bare(), stanza_type='groupchat')
        command_node = m.add_new_content(None, 'command')
        command_node.newChild(None, 'command', 'refresh')

        stream = self.room_state.manager.stream
        stream.send(m)

    # Party presence, mostly stored for new joiners
    def show_presence(self):
        p = Presence(to_jid=self.room_state.room_jid, status='lobby')
        args_node = p.add_new_content(None, 'args')
        args_node.newChild(None, 'alias', self.bot_nick)
        args_node.newChild(None, 'aliasPrintable', urllib.quote(self.bot_nick))
        args_node.newChild(None, 'cache', self.ia_avatarcache)
        args_node.newChild(None, 'location', urllib.quote('Ashburn, VA, US'))
        args_node.newChild(None, 'tagline', 'Legions Server')
        args_node.newChild(None, 'anonymous', '0')
        canhost_node = args_node.newChild(None, 'canHost', 'true')
        canhost_node.setProp('type', 'boolean')
        # maxplayers_node = args_node.newChild(None, 'maxplayers', str(self.size_limit))
        # maxplayers_node.setProp('type', 'number')
        args_node.newChild(None, 'state', self.state)

        stream = self.room_state.manager.stream
        stream.send(p)

    def user_left(self, user, stanza):
        MucRoomHandler.user_left(self, user, stanza)

        print "*** User left: %s" % user.nick

        # Why doesn't pyxmpp delete it?
        if user.nick in self.room_state.users:
            del self.room_state.users[user.nick]

        self.shazbot_update_usercount()

    def shazbot_update_usercount(self):
        stream = self.room_state.manager.stream
        num_users = len(self.room_state.users)

        self.game_handler.update_playercount(num_users)

        for i in self.room_state.users:
            print "USER:", i, self.room_state.users[i], self.room_state.users[i].presence
        if self.private:
            room_id = ''
        else:
            room_id = self.room_state.room_jid.node
        p = Presence(
            status="Online:|%s||Home|Hosting Party|%d|%d|%sZ|false" % (
                room_id, num_users, self.size_limit,
                datetime.utcnow().replace(microsecond=0).isoformat()))
        stream.send(p)

    def presence_changed(self, user, stanza):
        MucRoomHandler.presence_changed(self, user, stanza)
