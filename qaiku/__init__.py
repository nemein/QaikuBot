import inspect

from twisted.application import service
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish

from twisted.internet.task import LoopingCall

from wokkel import client, xmppim, component

from qaiku import commands
from sqlite3 import dbapi2 as sqlite
from markdown2 import markdown

USAGE = ()

class BotMessage(xmppim.MessageProtocol):
    def __init__(self, jid):
        self.jid = jid
        self.help = []
        self.connection = sqlite.connect('test.db')
        self.cursor = self.connection.cursor()
        self.commands = {}
        # Only get classes from commands file
        for (name, klass) in inspect.getmembers(commands, inspect.isclass):
            # If we are not dealing with the "baseclass"
            if name not in ('Command','datetime','time'):
                # Instanciate the class so we have a bound method
                instance = klass(self)
                self.commands[name] = instance
                # If the class is listed in commands with usage
                if name in USAGE:
                    if hasattr(klass, 'usage'):
                        self.help.append("%s %s" % (name, klass.usage))
            else:
                continue
        self.help = "\n".join(self.help)
        loop = LoopingCall(self.loop)
        loop.start(20, False)
        
    def connectionMade(self):
        super(BotMessage, self).connectionMade()

    def loop(self):
        for key in self.commands:
            self.commands[key].loop()

    def execcmd(self, command, msg, *args):
        command = self.commands.get(command, self.commands['default'])
        command.sender = msg['from']
        command.sender_jid = msg['from'].rsplit('/')[0]
        command.run(msg, *args)
    
    # Helper for creating replies
    def reply(self, jid, content):
        msg = domish.Element((None, "message"))
        msg['to'] = jid
        msg['from'] = self.jid.full()
        msg['type'] = 'chat'
        msg.addUniqueId()
        msg.addElement('body', content=content)
        body = domish.Element((None, 'body'))
        body.addRawXml(markdown(content))
        msg.addElement('html', defaultUri='http://jabber.org/protocol/xhtml-im', content=body)
        self.send(msg)
    
    def onMessage(self, msg):
        if not isinstance(msg.body, domish.Element):
            return None
        
        text = unicode(msg.body).encode('utf-8').strip()
        cmdargs = text.split()
        cmd = cmdargs[0]
        args = cmdargs[1:]
        self.execcmd(cmd, msg, *args)
        
class BotPresence(xmppim.PresenceClientProtocol):
    def __init__(self, jid):
        """docstring for __init__"""
        self.jid = jid
    
    def connectionMade(self):
        super(BotPresence, self).connectionMade()
    
    def availableReceived(self, entity, show=None, statuses=None, priority=0):
        if self.jid != entity.userhostJID():
            self.available(entity=entity)