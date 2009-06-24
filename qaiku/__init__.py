import inspect

from twisted.application import service
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish

from twisted.internet.task import LoopingCall

from wokkel import client, xmppim, component

from qaiku import commands
from sqlite3 import dbapi2 as sqlite
from markdown2 import markdown

USAGE = []
IGNORED_CMDS = ('Command','datetime','time')

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
            if name not in IGNORED_CMDS:
                # Instanciate the class so we have a bound method
                instance = klass(self)
                self.commands[name] = instance
                # If the class is listed in commands with usage
                if hasattr(instance, 'usage'):
                    USAGE.append(instance.usage)
            else:
                continue
        self.help = "\n\n".join(USAGE)
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
        self.jid = jid
    
    def connectionMade(self):
        super(BotPresence, self).connectionMade()
    
    def availableReceived(self, entity, show=None, statuses=None, priority=0):
        if self.jid != entity.userhostJID():
            self.available(entity=entity)
    
    def subscribedReceived(self, entity):
        print "subscribedReceived - %s" % (entity,)
        self.subscribed(entity=entity)
        jid = entity.userhost()
        msg = domish.Element((None, "message"))
        msg['to'] = jid
        msg['from'] = self.jid.full()
        msg['type'] = 'chat'
        msg.addUniqueId()
        reply = """Hello there!\n\nYou are receiving this message, because you have just added me as your buddy.\n\nI would like to inform you that the commands which I accept are as follows:"""
        cmds = "\n\n".join(USAGE)
        msg.addElement('body', content="%s\n\n%s" % (reply, cmds))
        self.send(msg)
    
    def unsubscribedReceived(self, entity):
        print "unsubscribedReceived - %s" % (entity,)
        self.unsubscribed(entity)
        
    def subscribeReceived(self, entity):
        print "subscribeReceived - %s" % (entity,)
        self.subscribe(entity)
        
    def unsubscribeReceived(self, entity):
        print "unsubscribeReceived - %s" % (entity,)
        self.unsubscribe(entity)
