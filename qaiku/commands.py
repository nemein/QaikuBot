# -*- coding: utf-8 -*-
import urllib, urllib2
import simplejson as json
from datetime import datetime
from time import gmtime, mktime, strptime

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
LAST_MSGS = {}

class Command(object):
    def __init__(self, parent):
        self.parent = parent
        self.sender = ''
        self.sender_jid = ''
        self.cursor = parent.cursor
        self.connection = parent.connection
        LAST_MSGS = {}
    
    def send(self, user, plaintext, markdownized=None):
        self.parent.reply(user, plaintext, markdownized)
    
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
    
    def run(self, message, *args):
        self.reply('Command undefined, try "HELP" for a listing of available commands.')
  
class default(Command):
    def __init__(self, parent):
        super(default, self).__init__(parent)
    
    def run(self, message, *args):
        apikey = self.get_apikey()
        if apikey is None:
            print "No API key for user %s" % (self.sender_jid,)
            return None
        # elif not args or not args[0]:
        #     self.reply('No message given.')
        #     return None
        
        msg = unicode(message.body)

        if msg.startswith('@'):
            cmdargs = msg.split()
            username = cmdargs[0]
            try:
                user = LAST_MSGS[self.sender_jid]
            except KeyError:
                self.reply("It appears I have no recollection of Qaikus you have received before, so I am sending your message along as new Qaiku. You should start following something so I serve you better.")
                self._publish(apikey, message.body)
                return None

            try:
                as_reply_to = LAST_MSGS[self.sender_jid]['users'][username[1:]]
            except KeyError:
                self.reply("It appears I have no recollection of Qaikus from %s before, so I am sending your message along as new Qaiku." % username)
                self._publish(apikey, msg)
            
            self._publish(apikey, msg, reply_to=as_reply_to)
        else:
            self._publish(apikey, msg)

    def _publish(self, apikey, message, reply_to=None):
        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
        try:
            data = urllib.urlencode({'status': unicode(message).encode('utf-8')})
            params = urllib.urlencode({'apikey': apikey})
            if reply_to is not None:
                data = urllib.urlencode({'status': unicode(message).encode('utf-8'), 'in_reply_to_status_id': reply_to })
        
            url = 'http://www.qaiku.com/api/statuses/update.json?%s' % params
            req = opener.open(url, data)
            response = req.read()
        except urllib2.HTTPError, e:
            print "Updating failed for user %s, HTTP %s" % (self.sender_jid, e.code)
        except urllib2.URLError, e:
            print "Connection failed for user %s, error %s" % (self.sender_jid, e.message)
    
class AUTHORIZE(Command):
    def __init__(self, parent):
        super(AUTHORIZE, self).__init__(parent)
        self.sql('CREATE TABLE IF NOT EXISTS qaikubot_authorize (id INTEGER PRIMARY KEY, name VARCHAR(50), jid VARCHAR(50), apikey VARCHAR(50))')
        self.usage = '"AUTHORIZE apikey" connects your instant messaging account to your Qaiku account, after which you can issue other commands.'

    def run(self, message, *args):
        if not args or not args[0]:
            self.reply('need API key')
            return None

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
        try:
            params = urllib.urlencode({'apikey': args[0]})
            url = 'http://www.qaiku.com/api/statuses/user_timeline.json?%s' % params
            req = opener.open(url)
        except urllib2.HTTPError, e:
            self.reply('Sorry, authorization failed.')
            return None
        except urllib2.URLError, e:
            print "Connection failed, error %s" % (e.message)
            self.reply("Connection failed, error %s. Try again later" % (e.message))
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
 
class FOLLOW(Command):
    def __init__(self, parent):
        super(FOLLOW, self).__init__(parent)
        self.sql('CREATE TABLE IF NOT EXISTS qaikubot_follow (id INTEGER PRIMARY KEY, jid VARCHAR(50), follow_type VARCHAR(50), last_updated INTEGER(11))')
        self.recordsperloop = 10
        self.offset = 0
        self.recordcount = 1
        self.usage = '"FOLLOW target" adds the target (radar, stream, @nickname, #channel) to your follow list, after which you start to receive Qaikus from the target. Alternatively, issuing "FOLLOW" without arguments returns your list of FOLLOWs.'
        
    def run(self, message, *args):
        if not args or not args[0]:
            values = (self.sender_jid,)
            self.cursor.execute("SELECT follow_type FROM qaikubot_follow WHERE jid = ? ORDER BY follow_type ASC", values)
            results = self.cursor.fetchall()
            self.reply('Your current FOLLOWs are: %s' % (', '.join([follow[0] for follow in results])))
            return None
        
        # See if this already exists
        values = (self.sender_jid, args[0])
        self.cursor.execute("SELECT last_updated FROM qaikubot_follow WHERE jid = ? AND follow_type = ?", values)
        result = self.cursor.fetchone()
        apikey = self.get_apikey(self.sender_jid)
        follow_type = args[0]

        if result is not None:
            # Follow already exists, do nothing.
            pass
        else:
            if follow_type == 'stream' or follow_type == 'radar':
                self.reply('Following %s' % (follow_type,))
            elif follow_type.startswith('#'):
                self.reply('Following channel %s' % args[0])
            elif follow_type.startswith('@'):
                opener = urllib2.build_opener()
                opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
                try:
                    params = urllib.urlencode({'apikey': apikey, 'screen_name': follow_type[1:]})
                    url = 'http://www.qaiku.com/api/statuses/user_timeline.json?%s' % params
                    req = opener.open(url)
                except urllib2.HTTPError, e:
                    # Authorization failed for user, complain?
                    # TODO: deactivate all subscriptions for the user until he reauthorizes
                    self.reply('User %s does not exist.' % follow_type[1:])
                    return None
                except urllib2.URLError, e:
                    print "Connection failed, error %s" % (e.message)
                    self.reply("Connection failed, error %s. Try again later" % (e.message))
                    return None

                    
                if req.read() == '[]':
                    self.reply("%s's feed is private and therefore cannot be followed." % (follow_type[1:],))
                    return None
                else:
                    self.reply('Following %s' % follow_type[1:])
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
        self.cursor.execute("SELECT count(id) FROM qaikubot_follow")
        self.recordcount = self.cursor.fetchone()[0]

        user_messages = {}
        
        for follow_type, jid, last_updated in results:
            apikey = self.get_apikey(jid)
            if apikey is None:
                print "No API key for user %s" % (jid,)
                continue
            
            if jid not in user_messages:
                user_messages[jid] = {}
                user_messages[jid]['messages'] = {}
                user_messages[jid]['order'] = []
            
            if jid not in LAST_MSGS:
                LAST_MSGS[jid] = {}
                LAST_MSGS[jid]['users'] = {}
            
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
                    else:
                        req = opener.open('http://www.qaiku.com/api/statuses/friends_timeline.json?apikey=%s' % apikey)
                except urllib2.HTTPError, e:
                    # Authorization failed for user, complain?
                    # TODO: deactivate all subscriptions for the user until he reauthorizes
                    print "STREAM Authorization failed for user %s with API key %s on FOLLOW %s (HTTP Error %s)" % (jid,apikey,follow_type,e.code)
                    plaintext_reply = "Sorry, your FOLLOW for %s could not be read, this is probably due to bad apikey." % (follow_type)
                    self.send(jid, plaintext_reply)
                    continue
                except urllib2.URLError, e:
                    print "Connection failed, error %s" % (e.message)
                    self.reply("Connection failed, error %s. Try again later" % (e.message))
                    return None

                
                try:
                    messages = json.loads(req.read())
                except ValueError, e:
                    print "Looks like there's a problem with the %s API: %s" (follow_type, e.message,)
                    continue
                
                messages.reverse()
                latestupdate = last_updated
                for message in messages:
                    if not message['user']:
                        continue
                    markdown_username = self._link_to_msg(message)
                    markdownized = "%s: %s" % (markdown_username, message['text'])
                    plaintext = "%s: %s" % (message['user']['screen_name'], message['text'])
                    
                    # TODO: There must be a more elegant way for parsing the funky date format
                    createdat = int(mktime(strptime(message['created_at'], '%a %b %d %H:%M:%S +0000 %Y')))
                    
                    if createdat > latestupdate:
                        # We use timestamp from the messages in order to avoid gaps due to Qaiku and local machine being in different time
                        latestupdate = createdat
                    
                    if message['id'] not in user_messages[jid]['messages']:
                        user_messages[jid]['messages'][message['id']] = {'plaintext': plaintext, 'markdown': markdownized}
                        user_messages[jid]['order'].append((createdat, message['id']))
                        if message['in_reply_to_status_id']:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['in_reply_to_status_id']
                        else:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['id']
                    
                values = (latestupdate, jid, follow_type)
                self.cursor.execute("UPDATE qaikubot_follow SET last_updated = ? WHERE jid = ? AND follow_type = ?", values)
                self.connection.commit()
            elif follow_type == 'radar':
                opener = urllib2.build_opener()
                opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
                try:
                    if last_updated is not None:
                        in_datetime = datetime.fromtimestamp(last_updated)
                        since = in_datetime.strftime('%Y-%m-%d %H:%M:%S')
                        params = urllib.urlencode({'apikey': apikey, 'since': since})
                        url = 'http://www.qaiku.com/api/statuses/mentions.json?%s' % params
                        req = opener.open(url)
                    else:
                        req = opener.open('http://www.qaiku.com/api/statuses/mentions.json?apikey=%s' % apikey)
                except urllib2.HTTPError, e:
                    # Authorization failed for user, complain?
                    # TODO: deactivate all subscriptions for the user until he reauthorizes
                    print "RADAR Authorization failed for user %s with API key %s (HTTP Error %s)" % (jid,apikey,e.code)
                    continue
                except urllib2.URLError, e:
                    print "Connection failed, error %s" % (e.message)
                    continue

                try:
                    messages = json.loads(req.read())
                except ValueError, e:
                    print "Looks like there's a problem with the %s API: %s" (follow_type, e.message,)
                    continue
                
                messages.reverse()
                latestupdate = last_updated
                for message in messages:
                    if not message['user']:
                        continue
                    markdown_username = self._link_to_msg(message)
                    markdownized = "%s: %s" % (markdown_username, message['text'])
                    plaintext = "%s: %s" % (message['user']['screen_name'], message['text'])
                    
                    # TODO: There must be a more elegant way for parsing the funky date format
                    createdat = int(mktime(strptime(message['created_at'], '%a %b %d %H:%M:%S +0000 %Y')))
                    
                    if createdat > latestupdate:
                        # We use timestamp from the messages in order to avoid gaps due to Qaiku and local machine being in different time
                        latestupdate = createdat
                    
                    if message['id'] not in user_messages[jid]['messages']:
                        user_messages[jid]['messages'][message['id']] = {'plaintext': plaintext, 'markdown': markdownized}
                        user_messages[jid]['order'].append((createdat, message['id']))
                        if message['in_reply_to_status_id']:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['in_reply_to_status_id']
                        else:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['id']
                    
                values = (latestupdate, jid, follow_type)
                self.cursor.execute("UPDATE qaikubot_follow SET last_updated = ? WHERE jid = ? AND follow_type = ?", values)
                self.connection.commit()
            elif follow_type.startswith('@'):
                opener = urllib2.build_opener()
                opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
                try:
                    if last_updated is not None:
                        in_datetime = datetime.fromtimestamp(last_updated)
                        since = in_datetime.strftime('%Y-%m-%d %H:%M:%S')
                        params = urllib.urlencode({'apikey': apikey, 'screen_name': follow_type[1:], 'since': since})
                        url = 'http://www.qaiku.com/api/statuses/user_timeline.json?%s' % params
                        req = opener.open(url)
                    else:
                        params = urllib.urlencode({'apikey': apikey, 'screen_name': follow_type[1:]})
                        url = 'http://www.qaiku.com/api/statuses/user_timeline.json?%s' % params
                        req = opener.open(url)
                except urllib2.HTTPError, e:
                    # Authorization failed for user, complain?
                    # TODO: deactivate all subscriptions for the user until he reauthorizes
                    print "@username Authorization failed for user %s with API key %s (HTTP Error %s)" % (jid,apikey,e.code)
                    continue
                except urllib2.URLError, e:
                    print "Connection failed, error %s" % (e.message)
                    continue
                    
                try:
                    messages = json.loads(req.read())
                except ValueError, e:
                    print "Looks like there's a problem with the %s API: %s" (follow_type, e.message,)
                    continue
                
                messages.reverse()
                latestupdate = last_updated
                for message in messages:
                    try:
                        if not message['user']:
                            continue
                    except NameError:
                        continue
                    markdown_username = self._link_to_msg(message)
                    markdownized = "%s: %s" % (markdown_username, message['text'])
                    plaintext = "%s: %s" % (message['user']['screen_name'], message['text'])
                    
                    createdat = int(mktime(strptime(message['created_at'], '%a %b %d %H:%M:%S +0000 %Y')))
                    
                    if createdat > latestupdate:
                        # We use timestamp from the messages in order to avoid gaps due to Qaiku and local machine being in different time
                        latestupdate = createdat

                    if message['id'] not in user_messages[jid]['messages']:
                        user_messages[jid]['messages'][message['id']] = {'plaintext': plaintext, 'markdown': markdownized}
                        user_messages[jid]['order'].append((createdat, message['id']))
                        if message['in_reply_to_status_id']:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['in_reply_to_status_id']
                        else:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['id']
                    
                values = (latestupdate, jid, follow_type)
                self.cursor.execute("UPDATE qaikubot_follow SET last_updated = ? WHERE jid = ? AND follow_type = ?", values)
                self.connection.commit()
            elif follow_type.startswith('#'):
                opener = urllib2.build_opener()
                opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
                try:
                    if last_updated is not None:
                        in_datetime = datetime.fromtimestamp(last_updated)
                        since = in_datetime.strftime('%Y-%m-%d %H:%M:%S')
                        params = urllib.urlencode({'apikey': apikey, 'since': since})
                        url = 'http://www.qaiku.com/api/statuses/channel_timeline/%s.json?%s' % (follow_type[1:], params)
                        req = opener.open(url)
                    else:
                        params = urllib.urlencode({'apikey': apikey })
                        url = 'http://www.qaiku.com/api/statuses/channel_timeline/%s.json?%s' % (follow_type[1:], params)
                        req = opener.open(url)
                except urllib2.HTTPError, e:
                    # Authorization failed for user, complain?
                    # TODO: deactivate all subscriptions for the user until he reauthorizes
                    print "#channel Authorization failed for user %s with API key %s (HTTP Error %s)" % (jid,apikey,e.code)
                    continue
                except urllib2.URLError, e:
                    print "Connection failed, error %s" % (e.message)
                    continue

                try:
                    messages = json.loads(req.read())
                except ValueError, e:
                    print "Looks like there's a problem with the %s API: %s" (follow_type, e.message,)
                    continue

                messages.reverse()
                latestupdate = last_updated
                for message in messages:
                    if not message['user']:
                        continue
                    markdown_username = self._link_to_msg(message)
                    markdownized = "%s: %s" % (markdown_username, message['text'])
                    plaintext = "%s: %s" % (message['user']['screen_name'], message['text'])
                    
                    createdat = int(mktime(strptime(message['created_at'], '%a %b %d %H:%M:%S +0000 %Y')))
                    
                    if createdat > latestupdate:
                        # We use timestamp from the messages in order to avoid gaps due to Qaiku and local machine being in different time
                        latestupdate = createdat

                    if message['id'] not in user_messages[jid]['messages']:
                        user_messages[jid]['messages'][message['id']] = {'plaintext': plaintext, 'markdown': markdownized}
                        user_messages[jid]['order'].append((createdat, message['id']))
                        if message['in_reply_to_status_id']:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['in_reply_to_status_id']
                        else:
                            LAST_MSGS[jid]['users'][message['user']['screen_name']] = message['id']
                    
                values = (latestupdate, jid, follow_type)
                self.cursor.execute("UPDATE qaikubot_follow SET last_updated = ? WHERE jid = ? AND follow_type = ?", values)
                self.connection.commit()
            else:
                print "Not fetching FOLLOWed %s to %s as it is not implemented yet" % (follow_type, jid)
                continue
        
        for user in user_messages:
            for item in sorted(user_messages[user]['order']):
                self.send(user, user_messages[user]['messages'][item[1]]['plaintext'], user_messages[user]['messages'][item[1]]['markdown'])

        self.offset += self.recordsperloop
        if self.offset > self.recordcount:
            self.offset = 0
    
    def _link_to_msg(self, msg):
        try:
            channel = msg['channel']
        except KeyError, e:
            if e.message == 'channel':
                channel = None

        in_reply_to = msg['in_reply_to_status_id']
        
        if channel and in_reply_to:
            url = 'http://www.qaiku.com/channels/show/%s/view/%s/#%s' % (channel, in_reply_to, msg['id'])
        elif channel:
            url = 'http://www.qaiku.com/channels/show/%s/view/%s' % (channel, msg['id'])
        elif in_reply_to:
            url = '%sshow/%s/#%s' % (msg['user']['url'], in_reply_to, msg['id'])
        else:
            url = '%sshow/%s' % (msg['user']['url'], msg['id'])
                
        return "[%s](%s)" % (msg['user']['screen_name'], url)

class UNFOLLOW(Command):
    def __init__(self, parent):
        super(UNFOLLOW, self).__init__(parent)
        self.usage = '"UNFOLLOW target" removes the target (stream, @nickname) from your follow list, after which you no longer receive their Qaikus.'
    
    def run(self, message, *args):
        if not args or not args[0]:
            self.reply('No UNFOLLOW target given.')
            return None
        
        values = (self.sender_jid, args[0])
        self.cursor.execute("SELECT last_updated FROM qaikubot_follow WHERE jid = ? AND follow_type = ?", values)
        result = self.cursor.fetchone()
        
        if result is not None:
            values = (self.sender_jid, args[0])
            self.cursor.execute('DELETE FROM qaikubot_follow WHERE jid = ? AND follow_type = ?', values)
            self.connection.commit()
            self.reply('Quit following %s for you' % (args[0],))
        else:
            self.reply('You are not following %s' % (args[0],))

class LOCATION(Command):
    def __init__(self, parent):
        super(LOCATION, self).__init__(parent)
        self.usage = '"LOCATION placename, city, country" updates your Qaiku location to a given spot.'

    def run(self, message, *args):
        apikey = self.get_apikey()
        if apikey is None:
            print "No API key for user %s" % (self.sender_jid,)
            return None
        
        msg = unicode(message.body)
        location = msg.replace('LOCATION ', '')

        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', 'QaikuBot/0.1')]
        try:
            data = urllib.urlencode({'location': unicode(location).encode('utf-8')})
            params = urllib.urlencode({'apikey': apikey})
            url = 'http://www.qaiku.com/api/account/update_profile.json?%s' % params
            req = opener.open(url, data)
            response = req.read()
        except urllib2.HTTPError, e:
            print "Updating failed for user %s, HTTP %s" % (self.sender_jid, e.code)
            return None
        except urllib2.URLError, e:
            print "Connection failed for user %s, error %s" % (self.sender_jid, e.message)
            return None
        self.reply("Location updated to '%s'" % (location,))

class PING(Command):
    def __init__(self, parent):
        super(PING, self).__init__(parent)
        self.usage = '"PING" returns "PONG?" as a confirmation that everything is a-ok.'
    
    def run(self, message, *args):
        self.reply('PONG?')
        

class HELP(Command):
    def __init__(self, parent):
        super(HELP, self).__init__(parent)
        self.usage = '"HELP" lists the commands available to you.'
    
    def run(self, message, *args):
        self.send(self.sender, self.parent.help)