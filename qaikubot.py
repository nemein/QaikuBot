from twisted.application import service
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish
import ConfigParser

from wokkel import client, xmppim, component

from qaiku import BotPresence, BotMessage

config = ConfigParser.ConfigParser()
config.read('qaikubot.ini')

myjid = JID(config.get('qaikubot', 'jid'))
password = config.get('qaikubot', 'password')

application = service.Application('XMPP client')
xmppClient = client.XMPPClient(myjid, password)
xmppClient.logTraffic = False
xmppClient.setServiceParent(application)

presence = BotPresence(myjid)
presence.setHandlerParent(xmppClient)
presence.available(show='Online')

messages = BotMessage(myjid)
messages.setHandlerParent(xmppClient)