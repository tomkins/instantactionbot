import anydbm
import urllib
import urllib2
import cookielib


class IALogin(object):
    def __init__(self, user_agent, homepage_url, login_url, cache_file):
        self.user_agent = user_agent
        self.homepage_url = homepage_url
        self.login_url = login_url
        self.cache_file = cache_file

    # Returns the cached login if it exists
    def get_cached_login(self):
        db = anydbm.open(self.cache_file, 'c')

        if 'ticket' in db:
            ticket = db['ticket']
        else:
            ticket = None

        db.close()

        return ticket

    # Save login details for another time
    def save_login(self, ticket):
        db = anydbm.open(self.cache_file, 'c')
        db['ticket'] = ticket
        db.close()

    # Login to the IA site, specify cached as false incase of an authentication error
    def login(self, username, password, cached=True):
        # If we can use cached details, use it
        if cached:
            cached_login = self.get_cached_login()

            if cached_login:
                return cached_login

        # We need cookies for this to work, and sneak in as a different browser
        cookie_jar = cookielib.CookieJar()

        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))
        urllib2.install_opener(opener)

        opener.addheaders = [('User-agent', self.user_agent)]

        # Homepage first so we have cookies
        # print "Requesting: %s" % self.homepage_url
        request = urllib2.Request(self.homepage_url)
        urllib2.urlopen(request)

        # Login page
        login_data = urllib.urlencode({
            'login[login_email]': username,
            'login[login_password]': password,
        })

        # print "Requesting: %s" % self.login_url
        request = urllib2.Request(self.login_url, login_data)
        urllib2.urlopen(request)

        gg_ticket = None

        for cookie in cookie_jar:
            if cookie.name == 'ggticket':
                gg_ticket = urllib.unquote(cookie.value)
                break

        # Store it for future usage
        if gg_ticket:
            self.save_login(gg_ticket)

        # print "GG Ticket: %s" % gg_ticket

        return gg_ticket
