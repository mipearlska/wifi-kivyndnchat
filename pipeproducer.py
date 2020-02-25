import sys
import time
import argparse
import traceback
import random

from pyndn import Name
from pyndn import Data
from pyndn import Face
from pyndn.security import KeyChain

image = "test3.jpg"

def chunkstring(string, length):
    return (string[0+i:length+i] for i in range(0, len(string), length))

class Producer(object):

    def __init__(self, prefix, transferfile):
        self.keyChain = KeyChain()
        self.prefix = Name(prefix)
        self.isDone = False
        self.transferfile = transferfile

        # Initialize list for Data packet storage.
        # We'll treat the indices as equivalent to the sequence
        # number requested by Interests.
        self.data = []

        f = open(transferfile,'rb')
        imgdata = f.read()
        chunks = list(chunkstring(imgdata,8192))
        print len(chunks)

        finalBlock = Name.Component.fromNumberWithMarker(len(chunks) - 1, 0x00)
        hourMilliseconds = 3600 * 1000

        # Pre-generate and sign all of Data we can serve.
        # We can also set the FinalBlockID in each packet
        # ahead of time because we know the entire sequence.


        for i in range(0,len(chunks)):
            dataName = Name(prefix).appendSegment(i)
            print dataName

            data = Data(dataName)
            data.setContent(chunks[i])
            data.getMetaInfo().setFinalBlockID(finalBlock)
            data.getMetaInfo().setFreshnessPeriod(hourMilliseconds)

            self.keyChain.sign(data, self.keyChain.getDefaultCertificateName())

            self.data.append(data)



    def run(self):
        face = Face()

        # Use the system default key chain and certificate name to sign commands.
        face.setCommandSigningInfo(self.keyChain, self.keyChain.getDefaultCertificateName())

        # Also use the default certificate name to sign data packets.
        face.registerPrefix(self.prefix, self.onInterest, self.onRegisterFailed)

        print "Registering prefix %s" % self.prefix.toUri()

        while not self.isDone:
            face.processEvents()
            time.sleep(0.01)
        print "quit"



    def onInterest(self, prefix, interest, transport, registeredPrefixId):
        interestName = interest.getName()
        sequence = interestName[-1].toNumber()

        if 0 <= sequence and sequence < len(self.data):
            transport.send(self.data[sequence].wireEncode().toBuffer())

        print "Replied to: %s" % interestName.toUri()

        if sequence == len(self.data) -1:
            time.sleep(3)
            self.isDone = True


    def onRegisterFailed(self, prefix):
        print "Register failed for prefix", prefix.toUri()
        self.isDone = True






if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse command line args for ndn producer')
    parser.add_argument("-n", "--namespace", required=True, help='namespace to listen under')
    parser.add_argument("-f", "--file", required=False, help='file to transfer')

    args = parser.parse_args()

    try:
        namespace = args.namespace
        transferfile = args.file

        Producer(namespace, transferfile).run()

    except:
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
