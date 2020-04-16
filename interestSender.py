import sys
import time
import argparse
import traceback
import os

from pyndn import Interest
from pyndn import Name
from pyndn import Face

class Consumer(object):
    '''Register chat prefix to gateway router to advertise'''

    def __init__(self, HostName, prefixesToSend):
        self.host = Name(HostName)
        self.outstanding = dict()
        self.prefixesToSend = prefixesToSend
        self.isDone = False

        self.face = Face("127.0.0.1")

    def run(self):
        try:
            self._sendNextInterest(self.host)
            
            while not self.isDone:
                self.face.processEvents()
                time.sleep(0.01)

        except RuntimeError as e:
            print "ERROR: %s" %  e

    def _sendNextInterest(self, name):
        interest = Interest(name)
        uri = name.toUri()

        interest.setApplicationParameters(self.prefixesToSend)
        interest.setInterestLifetimeMilliseconds(4000)
        interest.setMustBeFresh(True)

        if uri not in self.outstanding:
            self.outstanding[uri] = 1

        self.face.expressInterest(interest, self._onData, self._onTimeout)
        print "Sent Chat Prefixes to host " + str(self.host)

    def _onData(self, interest, data):
        payload = data.getContent()
        name = data.getName()

        print str(self.host) + " recieved prefixes"
        del self.outstanding[name.toUri()]

        os.system("nfdc cs erase " + str(name))

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
    parser.add_argument("-u", "--uri", required=True, help='gateway router prefix')
    parser.add_argument("-p", "--prefixes", required=True, help='prefixes to send')

    args = parser.parse_args()

    try:
        uri = args.uri
        prefix = args.prefixes
        Consumer(uri,prefix).run()

    except:
        traceback.print_exc(file=sys.stdout)
        print "Error parsing command line arguments"
        sys.exit(1)