# -*- coding: utf-8 -*-
import urllib, urllib2
import simplejson as json
import locale, mx.DateTime
from datetime import datetime
from time import gmtime, mktime

# Basic command structure is as follows:
# class COMMAND_NAME_IN_CAPS(Command): - extend the base command class
#     def __init__(self, parent):
#         super(COMMAND_NAME_IN_CAPS, self).__init__(parent)
# 
#     def run(self, message, *args):
#         Do the command
# 
#     def loop(self):
#         Do what the command needs to do in a main loop
# 
#     def help(self):
#         Return the help/usage message

class Command(object):
    def __init__(self, parent):
        self.parent = parent
        self.sender = ''
        self.sender_jid = ''
        self.cursor = parent.cursor
        self.connection = parent.connection
    
    def send(self, user, message):
        self.parent.reply(user, message)
    
    def reply(self, message):
        self.send(self.sender, message)

    def sql(self, statement):
        self.cursor.execute(statement)
    
    def get_apikey(self, jid=None):
        if jid is None:
            jid = self.sender_jid
    
        self.cursor.execute("SELECT apikey FROM qaikubot_authorize WHERE jid = '%s'" % jid)
        result = self.cursor.fetchone()
        
        if result is not None:
            return result[0]
        else:
            return None

    def loop(self):
        return None
    
    def run(self):
        self.reply("Command undefined")
  
class default(Command):
    def __init__(self, parent):
        super(default, self).__init__(parent)
    
    # Publish a new Qaiku
    def run(self, message, *args):
        apikey = self.get_apikey()
        if apikey is None:
            print "No API key for user %s" % (self.sender_jid,)
            return None
            
        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
        try:
            data = urllib.urlencode({'status': unicode(message.body).encode('utf-8')})
            params = urllib.urlencode({'apikey': apikey})
            url = 'http://www.qaiku.com/api/statuses/update.json?%s' % params
            req = opener.open(url, data)
        except urllib2.HTTPError, e:
            print "Updating failed for user %s, HTTP %s" % (self.sender_jid, e.code)

class FOLLOW(Command):
    def __init__(self, parent):
        super(FOLLOW, self).__init__(parent)
        self.sql('CREATE TABLE IF NOT EXISTS qaikubot_follow (id INTEGER PRIMARY KEY, jid VARCHAR(50), follow_type VARCHAR(50), last_updated INTEGER(11))')
        self.recordsperloop = 5
        self.offset = 0
        self.recordcount = 1
        
    def run(self, message, *args):
        if not args or not args[0]:
            self.reply('No follow target given.')
            return None
        
        # See if this already exists
        values = (self.sender_jid, args[0])
        self.cursor.execute("SELECT last_updated FROM qaikubot_follow WHERE jid = ? AND follow_type = ?", values)
        result = self.cursor.fetchone()

        if result is not None:
            # Follow already exists, do nothing.
            pass
        else:
            if args[0] == 'stream':
                self.reply('Following stream')
            elif args[0].startswith('#'):
                self.reply('Following channel %s' % args[0])
            elif args[0].startswith('@'):
                self.reply('Following user %s' % args[0])
            else:
                # Do nothing
                self.reply('Unknown follow target, ignoring.')
                return None
            
            values = (self.sender_jid, args[0])
            self.cursor.execute("INSERT INTO qaikubot_follow (jid, follow_type) VALUES (?, ?)", values)
            self.connection.commit()
            
    def loop(self):        
        self.cursor.execute("SELECT follow_type, jid, last_updated FROM qaikubot_follow ORDER BY id ASC LIMIT %d OFFSET %d" % (self.recordsperloop, self.offset))
        results = self.cursor.fetchall()

        for follow_type, jid, last_updated in results:
            print "Looping FOLLOW %s for user %s" % (follow_type, jid)
            apikey = self.get_apikey(jid)
            if apikey is None:
                print "No API key for user %s" % (jid,)
                continue
            
            if follow_type == 'stream':
                opener = urllib2.build_opener()
                opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
                try:
                    if last_updated is not None:
                        in_datetime = datetime.fromtimestamp(last_updated)
                        since = in_datetime.strftime('%Y-%m-%d %H:%M:%S')
                        params = urllib.urlencode({'apikey': apikey, 'since': since})
                        url = 'http://www.qaiku.com/api/statuses/friends_timeline.json?%s' % params
                        req = opener.open(url)
                        print url
                    else:
                        req = opener.open('http://www.qaiku.com/api/statuses/friends_timeline.json?apikey=%s' % apikey)
                except urllib2.HTTPError:
                    # Authorization failed for user, complain?
                    # TODO: deactivate all subscriptions for the user until he reauthorizes
                    print "Authorization failed for user %s with API key %s" % (jid,apikey)
                    continue

                messages = json.loads(req.read())
                messages.reverse()
                latestupdate = last_updated
                for message in messages:
                    messageformatted = "%s: %s" % (message['user']['screen_name'], message['text'])
                    
                    # TODO: There must be a more elegant way for parsing the funky date format
                    loc = locale.getlocale(locale.LC_TIME)
                    locale.setlocale(locale.LC_TIME, 'C')
                    createdat = int(mx.DateTime.Parser.DateTimeFromString(message['created_at']))
                    locale.setlocale(locale.LC_TIME, loc)
                    
                    if createdat > latestupdate:
                        # We use timestamp from the messages in order to avoid gaps due to Qaiku and local machine being in different time
                        latestupdate = createdat

                    self.send(jid, messageformatted)

                values = (latestupdate, jid)
                self.cursor.execute("UPDATE qaikubot_follow SET last_updated = ? WHERE jid = ?", values)
                self.connection.commit()
                continue
            else:
                print "Not fetching FOLLOWed %s to %s as it is not implemented yet" % (follow_type, jid)
                continue

        self.offset += self.recordsperloop
        if self.offset > self.recordcount:
            self.offset = 0

class AUTHORIZE(Command):
    def __init__(self, parent):
        super(AUTHORIZE, self).__init__(parent)
        self.sql('CREATE TABLE IF NOT EXISTS qaikubot_authorize (id INTEGER PRIMARY KEY, name VARCHAR(50), jid VARCHAR(50), apikey VARCHAR(50))')
    
    def run(self, message, *args):
        if not args or not args[0]:
            self.reply('need API key')
            return None
        
        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
        try:
            params = urllib.urlencode({'apikey': args[0]})
            url = 'http://www.qaiku.com/api/statuses/user_timeline.json?%s' % params
            print url
            req = opener.open(url)
        except urllib2.HTTPError:
            self.reply('Sorry, authorization failed.')
            return None
        
        results = req.read() 
        try:
            reply = json.loads(results)
        except ValueError:
            self.reply('Sorry, authorization failed. Qaiku returned invalid data.')
            print results
            return None
        
        apikey = self.get_apikey()
        
        # If we already have a user, update their apikey, otherwise create a new record.
        if apikey is not None:
            if apikey == args[0]:
                self.reply('No action taken.')
            else:
                values = (args[0], self.sender_jid)
                self.cursor.execute("UPDATE qaikubot_authorize SET apikey = ? WHERE jid = ?", values)
                self.connection.commit()
                self.reply('Updated API key!')
        else:
            self.reply('Welcome %(username)s. Authorization successful!' % {'username': reply[0]['user']['name'] })
            values = (reply[0]['user']['name'], self.sender_jid, args[0])
            self.cursor.execute("INSERT INTO qaikubot_authorize (name, jid, apikey) VALUES (?, ?, ?)", values)
            # TODO: Activate all FOLLOWs of the user in case they were deactivated earlier
            self.connection.commit()