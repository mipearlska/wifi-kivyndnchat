import sys
import time
import argparse
import traceback
import os

from pyndn import Interest
from pyndn import Name
from pyndn import Face

class Consumer(object):
    '''Hello World consumer'''

    def __init__(self, gatewayprefix, newprefix, chatroom):
        self.gatewayprefix = Name(gatewayprefix)
        self.newprefix = str(Name(newprefix))
        self.chatroom = str(Name(chatroom))
        self.parameter = self.newprefix +"|"+ self.chatroom
        self.outstanding = dict()
        self.isDone = False

        self.face = Face("127.0.0.1")



    def run(self):
        os.system("nlsrc advertise " + self.newprefix)
        os.system("nlsrc advertise " + self.chatroom)
        try:
            self._sendNextInterest(self.gatewayprefix)
            
            while not self.isDone:
                self.face.processEvents()
                time.sleep(0.01)

        except RuntimeError as e:
            print "ERROR: %s" %  e


    def _sendNextInterest(self, name):
        interest = Interest(name)
        uri = name.toUri()

        interest.setApplicationParameters(self.parameter)
        interest.setInterestLifetimeMilliseconds(4000)
        interest.setMustBeFresh(True)

        if uri not in self.outstanding:
            self.outstanding[uri] = 1

        self.face.expressInterest(interest, self._onData, self._onTimeout)
        print "Sent Interest for %s" % uri
        print interest


    def _onData(self, interest, data):
        payload = data.getContent()
        name = data.getName()

        print "Received response from gateway: ", payload.toRawStr()
        del self.outstanding[name.toUri()]

        self.isDone = True


    def _onTimeout(self, interest):
        name = interest.getName()
        uri = name.toUri()

        print "TIMEOUT #%d: %s" % (self.outstanding[uri], uri)
        self.outstanding[uri] += 1

        if self.outstanding[uri] <= 1000:
            self._sendNextInterest(name)
        else:
            self.isDone = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parse command line args to register new prefix')
    parser.add_argument("-u", "--uri", required=True, help='gateway prefix')
    parser.add_argument("-p", "--prefix", required=True, help='multicast prefix to register')
    parser.add_argument("-c", "--chatroom", required=True, help='chat channel prefix')

    args = parser.parse_args()

    try:
        uri = args.uri
        prefix = args.prefix
        chatroom = args.chatroom
        Consumer(uri,prefix,chatroom).run()

    except:
        traceback.print_exc(file=sys.stdout)
        print "Error parsing command line arguments"
        sys.exit(1)
