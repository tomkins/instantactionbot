from threading import Thread, Event
import Queue
import sqlite3
import time
import urllib
import urllib2


class StatsThread(Thread):
    def __init__(self, database, urls, retry):
        super(StatsThread, self).__init__()
        self.exit_event = Event()
        self.incoming_stats = Queue.Queue()
        self.db = None

        self.database_file = database
        self.urls = urls
        self.retry = '%d seconds' % retry

    def init_db(self):
        cur = self.db.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS xmldata(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, lastattempt DATETIME, nextattempt DATETIME, data_id INTEGER REFERENCES xmldata(id))""")
        cur.execute("""CREATE INDEX IF NOT EXISTS requests_data_id ON requests(data_id)""")
        cur.execute("""CREATE INDEX IF NOT EXISTS requests_nextattempt ON requests(nextattempt)""")
        cur.execute("""CREATE TRIGGER IF NOT EXISTS prune_requests AFTER DELETE ON requests
            BEGIN
                DELETE FROM xmldata WHERE id IN (SELECT xmldata.id FROM xmldata LEFT JOIN requests ON requests.data_id=xmldata.id WHERE requests.id IS NULL);
            END""")

    def exit(self, wait=False):
        self.exit_event.set()
        if wait:
            self.join()

    def run(self):
        self.db = sqlite3.connect(self.database_file, isolation_level='IMMEDIATE')
        self.init_db()

        while True:
            self.loop()

            if self.exit_event.isSet():
                break

        self.db.close()

    def loop(self):
        self.upload_data()

        try:
            cur = self.db.cursor()

            while True:
                data = self.incoming_stats.get(timeout=1)

                cur.execute("""INSERT INTO xmldata VALUES (NULL, ?)""", (data,))
                data_id = cur.lastrowid

                for i in self.urls:
                    cur.execute("""INSERT INTO requests VALUES (NULL, ?, NULL, datetime('now'), ?)""", (i, data_id))

                self.db.commit()

        except Queue.Empty:
            pass

    def upload_data(self):
        cur = self.db.cursor()

        # Only one at a time so we don't spend too long doing multiple requests
        cur.execute("""SELECT requests.id,url,xmldata.data FROM requests LEFT JOIN xmldata ON requests.data_id=xmldata.id WHERE datetime('now')>nextattempt ORDER BY nextattempt ASC, lastattempt ASC LIMIT 1""")

        for request_id, url, xml_data in cur:
            stats_data = urllib.urlencode({
                'data': xml_data,
            })

            print "Requesting: %s" % (url,)
            request = urllib2.Request(url, stats_data)

            try:
                urllib2.urlopen(request)
                print "Success!"
                cur.execute("""DELETE FROM requests WHERE id=?""", (request_id,))

            except urllib2.HTTPError:
                print "Fail!"
                cur.execute("""UPDATE requests SET lastattempt=datetime('now'), nextattempt=datetime('now', ?) WHERE id=?""", (self.retry, request_id))

            finally:
                self.db.commit()

    def add_stats(self, data):
        self.incoming_stats.put(data)
