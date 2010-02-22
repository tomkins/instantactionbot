#! /usr/bin/env python
#
# Copyright Alex Tomkins 2010
#
# Redistribution is prohibited (contact me for permission)
# Modifications are permitted (but don't redistribute)
#
import sys
import logging
import locale
import codecs
import time
import asyncore
from optparse import OptionParser
import ConfigParser

from iabot.bot import IAJabberBot
from iabot.jabber.stats import StatsThread


# Ensure we use the right encoding for the terminal
locale.setlocale(locale.LC_CTYPE, '')
encoding = locale.getlocale()[1]
if not encoding:
    encoding = 'us-ascii'
sys.stdout = codecs.getwriter(encoding)(sys.stdout, errors='replace')
sys.stderr = codecs.getwriter(encoding)(sys.stderr, errors='replace')


# PyXMPP uses `logging` module for its debug output
# applications should set it up as needed
logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)  # change to DEBUG for higher verbosity


# Command line config options
parser = OptionParser(usage='%prog conffile', version='%prog 0.1')
(options, args) = parser.parse_args()
if len(args) != 1:
    parser.error('Incorrect number of arguments')
config_filename = args[0]


# Load the relevant config file
config_file = ConfigParser.SafeConfigParser()
config_file.read([config_filename])


bot = IAJabberBot(config_file)
bot.connect()

try:
    last_idle = time.time()

    while True:
        asyncore.loop(timeout=1, count=1)

        # Try to call idle once every second
        if time.time() >= last_idle+1:
            bot.idle()
            last_idle = time.time()
except KeyboardInterrupt:
    print u"disconnecting..."
    bot.disconnect()

    if bot.stats_thread:
        bot.stats_thread.exit()

print u"exiting..."
