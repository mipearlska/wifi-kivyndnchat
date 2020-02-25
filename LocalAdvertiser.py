import sys
import time
import argparse
import traceback
import random
import os
import subprocess

from pyndn import Name
from pyndn import Data
from pyndn import Face
from pyndn.security import KeyChain




class Producer(object):
    def __init__(self):
        self.keyChain = KeyChain()
        self.isDone = False
        self.prefixesList = []
        self.gatewayIP = "gatewayIP"

    def run(self, namespace):
        # Create a connection to the local forwarder over a Unix socket
        self.gatewayIP = os.popen('ip route | grep default').read().split(" ")[2]+"02" #get gateway IP of gateway router
        os.system("nfdc face create remote udp://"+self.gatewayIP)
        os.system("nfdc route add /ndnchat/register udp://"+self.gatewayIP)
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
            # check gatewayIP change. If change:
            # Add route from UE to new gateway for each prefix in local prefix list
            # Concat prefix in the list to the form "prefix1|prefix2", then call interestSender to send them to new gateway router
            gatewayIP = os.popen('ip route | grep default').read().split(" ")[2]+"02"
            if gatewayIP != self.gatewayIP:
                os.system("nfdc face create remote udp://"+gatewayIP)
                os.system("nfdc route add /ndnchat/register udp://"+self.gatewayIP)
                concatPrefixesList = ""
                for i in range (0,len(self.prefixesList)):
                    os.system("nfdc route add " + str(self.prefixesList[i]) + " udp://" + gatewayIP)
                    if i == len(self.prefixesList) - 1:
                        concatPrefixesList = concatPrefixesList + self.prefixesList[i]
                    else:
                        concatPrefixesList = concatPrefixesList + self.prefixesList[i] + "|"
                subprocess.call(["python", "interestSender.py", "-u /ndnchat/register", "-p"+concatPrefixesList])
                self.gatewayIP = gatewayIP

            face.processEvents()
            time.sleep(0.01)


    def onInterest(self, prefix, interest, transport, registeredPrefixId):
        interestName = interest.getName()
        interestParams = str(interest.getApplicationParameters())
        addPrefixes = interestParams.split("|")

        # For each Prefix recieved save it in local array
        # Add route for that prefix from User to gateway router
        for i in range (0,len(addPrefixes)):
            self.prefixesList.append(str(addPrefixes[i]))
            os.system("nfdc route add " + str(addPrefixes[i]) + " udp://" + self.gatewayIP)

        # Send prefixesList to gateway router
        subprocess.call(["python", "interestSender.py", "-u /ndnchat/register", "-p"+interestParams])

        data = Data(interestName)
        data.setContent("Register Successful")

        hourMilliseconds = 3600 * 1000
        data.getMetaInfo().setFreshnessPeriod(hourMilliseconds)

        self.keyChain.sign(data, self.keyChain.getDefaultCertificateName())

        transport.send(data.wireEncode().toBuffer())

        print "Replied to: %s" % interestName.toUri()
        print msg
        
        self.isDone = True


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