from twisted.application import service
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish

from wokkel import client, xmppim, component

from qaiku import BotPresence, BotMessage

myjid = JID("testiapina@jabber.org")
password = 'salainensana'

application = service.Application('XMPP client')
xmppClient = client.XMPPClient(myjid, password)
xmppClient.logTraffic = False
xmppClient.setServiceParent(application)

presence = BotPresence(myjid)
presence.setHandlerParent(xmppClient)
presence.available(show='Online')

messages = BotMessage(myjid)
messages.setHandlerParent(xmppClient)