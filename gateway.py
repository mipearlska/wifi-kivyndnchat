import sys
import time
import argparse
import traceback
import random
import os

from pyndn import Name
from pyndn import Data
from pyndn import Face
from pyndn.security import KeyChain




class Producer(object):
    def __init__(self):
        self.keyChain = KeyChain()
        self.isDone = False


    def run(self, namespace):
        # Create a connection to the local forwarder over a Unix socket
        face = Face()

        prefix = Name(namespace)

        # Use the system default key chain and certificate name to sign commands.
        face.setCommandSigningInfo(self.keyChain, \
                                  self.keyChain.getDefaultCertificateName())

        # Also use the default certificate name to sign Data packets.
        face.registerPrefix(prefix, self.onInterest, self.onRegisterFailed)

        print "Registering prefix", prefix.toUri()

        # Run the event loop forever. Use a short sleep to
        # prevent the Producer from using 100% of the CPU.
        while not self.isDone:
            face.processEvents()
            time.sleep(0.01)



    def onInterest(self, prefix, interest, transport, registeredPrefixId):
        interestName = interest.getName()
        msg = str(interest.getApplicationParameters())
        print msg
        newprefix = msg.split("|")[0]
        channelprefix = msg.split("|")[1]

        os.system("nfdc route add " + newprefix + " 263")
        os.system("nfdc route add " + newprefix + " 265")
        os.system("nfdc route add " + channelprefix + " 263")
        os.system("nfdc route add " + channelprefix + " 265")
        os.system("nlsrc advertise " + newprefix)
        os.system("nlsrc advertise " + channelprefix)

        data = Data(interestName)
        data.setContent("Register Successful")

        hourMilliseconds = 3600 * 1000
        data.getMetaInfo().setFreshnessPeriod(hourMilliseconds)

        self.keyChain.sign(data, self.keyChain.getDefaultCertificateName())

        transport.send(data.wireEncode().toBuffer())

        print "Replied to: %s" % interestName.toUri()
        print msg


    def onRegisterFailed(self, prefix):
        print "Register failed for prefix", prefix.toUri()
        self.isDone = True






if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse command line args for ndn producer')
    parser.add_argument("-n", "--namespace", required=True, help='namespace to listen under')

    args = parser.parse_args()

    try:
        namespace = args.namespace
        Producer().run(namespace)

    except:
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
