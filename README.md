# InstantAction bot

## The past

Back in 2008, GarageGames/InstantAction launched instantaction.com, a browser
based gaming platform. Vaguely similar to Steam, all you had to do was install
their plugin, visit the site, and it would download and launch any games they
had to offer.

Fallen Empire: Legions was also launched on the InstantAction platform during
2008. However as it wasn't a great commercial success, the number of updates to
the game slowly dwindled. However one big pain with the game is that the only
dedicated servers available were public servers, so if you wanted to host a
private match it would be hosted from your home connection - not great for most
people on ADSL/cable connections.

At the end of 2009, I decided to reverse engineer how the InstantAction site
and their games worked. After a few weeks of effort and help from a few people,
we managed to get a Legions dedicated server running with players being able to
join the game - we could finally have proper matches running on dedicated
servers.

Thanks to the game being scriptable with TorqueScript, we continued to add more
features to Legions. We added tournament mode, new game types - Hunters and
Rabbit, stats, along with quite a few other tweaks.

Sadly in March 2010 the version of InstantAction which hosted Legions was shut
down whilst they were trying to save the company with a new version of the site
and platform, with games such as *The Secret of Monkey Island: Special Edition*
and *Instant Jam*. This all came to an end in November 2010 when InstantAction
announced they were shutting down.

## The code

This is the Python powered bot which acted as a bridge between the Legions game
server and the InstantAction XMPP server. Various features such as commands to
control the server, and stats reporting were added over time.

It required pyxmpp (version 1.0.1), Python libxml2, and ran under Python 2.5.

## Thanks to

**Mabel** - For your help in getting all of this running, and all the features
you added to the game.

**BugsPray** - For Hunters/Rabbit, we finally had some new game modes!

**TaylorBalbi** - For hosting the US servers, and for all the work you put into
the stats system.

Also thanks to the other people who helped, and to those who contributed to the
costs of the running the dedicated server to host the game servers.

## The present

Legions continues to live on as Legions: Overdrive, a free game available at
[legionsoverdrive.com](http://www.legionsoverdrive.com/).
