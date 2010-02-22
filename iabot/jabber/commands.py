from iabot.game import GameInProgress


class IAPartyCommands(object):
    def __init__(self, party, game):
        self.registered_commands = {
            'autostart': self.cmd_autostart,
            'map': self.cmd_map,
            'mode': self.cmd_mode,
            # 'teams': self.cmd_teams,
            'timelimit': self.cmd_timelimit,
            'scorelimit': self.cmd_scorelimit,
            'start': self.cmd_start,
            # 'stop': self.cmd_stop,
            'partysize': self.cmd_partysize,
            # 'load': self.cmd_load,
            'public': self.cmd_public,
            'private': self.cmd_private,
            'tournament': self.cmd_tournament,
            # 'kick': self.cmd_kick,
        }

        self.party = party
        self.game = game
        self.admins = []

    def get_command(self, command):
        if command in self.registered_commands:
            return self.registered_commands[command]
        else:
            return False

    def is_admin(self, nick):
        return nick.lower() in self.admins

    def cmd_autostart(self, user, args):
        if args.lower() == 'on':
            self.game.set_autostart(True)
            return 'Autostart is now: ENABLED'
        elif args.lower() == 'off':
            self.game.set_autostart(False)
            return 'Autostart is now: DISABLED'

    def cmd_tournament(self, user, args):
        if args.lower() == 'on':
            self.game.set_tournament(True)
            return 'Tournament mode is now: ENABLED'
        elif args.lower() == 'off':
            self.game.set_tournament(False)
            return 'Tournament mode is now: DISABLED'

    def cmd_map(self, user, args):
        try:
            self.game.set_level(args)
        except GameInProgress:
            return 'Unable to change settings whilst game is running.'

    def cmd_mode(self, user, args):
        try:
            self.game.set_mode(args)
        except GameInProgress:
            return 'Unable to change settings whilst game is running.'

    # def cmd_teams(self, user, args):
    #    try:
    #        if args.isdigit():
    #            new_teams = int(args)
    #
    #            self.game.set_teams(new_teams)
    #    except GameInProgress:
    #        return 'Unable to change settings whilst game is running.'

    def cmd_timelimit(self, user, args):
        try:
            if args.isdigit():
                new_limit = int(args)

                if new_limit > -1 and new_limit <= 60:
                    # We'll use 0 as unlimited
                    if new_limit == 0:
                        new_limit = -1

                    self.game.set_timelimit(new_limit)
        except GameInProgress:
            return 'Unable to change settings whilst game is running.'

    def cmd_scorelimit(self, user, args):
        try:
            if args.isdigit():
                new_limit = int(args)

                if new_limit > -1 and new_limit <= 10000:
                    # We'll use 0 as unlimited
                    if new_limit == 0:
                        new_limit = -1

                    self.game.set_scorelimit(new_limit)
        except GameInProgress:
            return 'Unable to change settings whilst game is running.'

    def cmd_start(self, user, args):
        try:
            if self.game.start_game():
                return 'Starting next map...'
        except GameInProgress:
            return 'Unable to start next map whilst game is running.'

    # def cmd_stop(self, user, args):
    #    if self.game_handler.stop_game():
    #        self.room_state.send_message('Stopping current map...')
    #    else:
    #        self.room_state.send_message('Unable to stop map (am I not running?)')

    # def cmd_load(self, user, args):
    #    with self.lock:
    #        if not self.loaded:
    #            self.load_game()

    # TODO: we really will load the game ourselves
    # def load_game(self):
    #    with self.lock:
    #        self.room_state.send_message('Loading Legions...')
    #        self.loaded = True
    #        self.set_state('loading')
    #        self.game_thread.start()

    def cmd_partysize(self, user, args):
        if args:
            if args.isdigit():
                new_limit = int(args)

                if new_limit >= 1 and new_limit <= 64:
                    self.party.party_settings(limit=new_limit)
                    return 'Party size is now: %d' % new_limit
                else:
                    args = None
            else:
                args = None

        if not args:
            return 'Party size is currently: %d' % self.size_limit

    def cmd_private(self, user, args):
        self.party.party_settings(private=True)
        return 'Party is now: PRIVATE'

    def cmd_public(self, user, args):
        self.party.party_settings(private=False)
        return 'Party is now: PUBLIC'

    def cmd_kick(self, user, args):
        if args.lower() in self.party.room_state.users:
            self.party.kick_user(args.lower())
            return 'Kicking %s' % args
        else:
            return 'User not in party'
