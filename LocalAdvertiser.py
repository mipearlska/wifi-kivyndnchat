import sys
import time
import argparse
import traceback
import random
import os
import subprocess
import socket

from pyndn import Name
from pyndn import Data
from pyndn import Face
from pyndn.security import KeyChain


def get_device_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8",80))
    return str(s.getsockname()[0])

class Producer(object):
    def __init__(self):
        self.keyChain = KeyChain()
        self.isDone = False
        self.prefixesList = []
        self.gatewayIP = "gatewayIP"
        self.gatewayFace = 0

    def run(self, namespace):
        # Create a connection to the local forwarder over a Unix socket
        self.gatewayIP = os.popen('ip route | grep default').read().split(" ")[2] #get gateway IP of gateway router
        os.system("ndn-autoconfig") #perform ndn-autoconfig create face to gateway router
        self.gatewayFace = os.popen('nfdc route list | grep localhost/nfd').read().split(" ")[1][8:]
        os.system("nfdc route add /ndnchat/register "+self.gatewayFace)
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
            # Delete old gatewayFace, add route from UE to new gateway for each prefix in local prefix list
            # Concat prefix in the list to the form "prefix1|prefix2", then call interestSender to send them to new gateway router
            try:
                newgatewayIP = os.popen('ip route | grep default').read().split(" ")[2]
                if newgatewayIP != self.gatewayIP:
                    os.system("nfdc face destroy "+self.gatewayFace)
                    print "Changes in network detected, attempt re-advertising prefixes"
                    os.system("ndn-autoconfig")
                    self.gatewayFace = os.popen('nfdc route list | grep localhost/nfd').read().split(" ")[1][8:]
                    os.system("nfdc route add /ndnchat/register "+self.gatewayFace)
                    concatPrefixesList = ""
                    for i in range (0,len(self.prefixesList)):
                        os.system("nfdc route add " + str(self.prefixesList[i]) + " " + self.gatewayFace)
                        if i == len(self.prefixesList) - 1:
                            concatPrefixesList = concatPrefixesList + self.prefixesList[i]
                        else:
                            concatPrefixesList = concatPrefixesList + self.prefixesList[i] + "|"
                    concatPrefixesList = concatPrefixesList + "|" + get_device_ip()
                    
                    subprocess.call(["python", "interestSender.py", "-u /ndnchat/register", "-p"+concatPrefixesList])
                    self.gatewayIP = newgatewayIP
            except IndexError:
                print "Lost Internet Connection"
                self.gatewayIP = ""

            face.processEvents()
            time.sleep(0.01)


    def onInterest(self, prefix, interest, transport, registeredPrefixId):
        interestName = interest.getName()
        interestParams = str(interest.getApplicationParameters())
        addPrefixes = interestParams.split("|")
        interestParams = interestParams + "|"+get_device_ip()
        # For each Prefix recieved save it in local array
        # Add route for that prefix from User to gateway router
        for i in range (0,len(addPrefixes)):
            print addPrefixes[i]
            self.prefixesList.append(str(addPrefixes[i]))
            os.system("nfdc route add " + str(addPrefixes[i]) + " " + self.gatewayFace)

        # Send prefixesList to gateway router
        subprocess.call(["python", "interestSender.py", "-u /ndnchat/register", "-p "+interestParams])

        data = Data(interestName)
        data.setContent("Register Successful")

        hourMilliseconds = 3600 * 1000
        data.getMetaInfo().setFreshnessPeriod(hourMilliseconds)

        self.keyChain.sign(data, self.keyChain.getDefaultCertificateName())

        transport.send(data.wireEncode().toBuffer())

        print "Sent advertisement to gateway router"
        
        #self.isDone = True


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
