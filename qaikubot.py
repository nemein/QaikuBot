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
apiurl = config.get('qaikubot', 'apiurl')

application = service.Application('QaikuBot')
xmppClient = client.XMPPClient(myjid, password)
xmppClient.logTraffic = False
xmppClient.setServiceParent(application)

presence = BotPresence(myjid)
presence.setHandlerParent(xmppClient)

messages = BotMessage(myjid)
messages.setApiUrl(apiurl)
messages.setHandlerParent(xmppClient)
