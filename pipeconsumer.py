import sys
import time
import argparse
import traceback

from pyndn import Interest
from pyndn import Name
from pyndn import Face


class Consumer(object):
    '''Hello World (extended) consumer'''

    def __init__(self, prefix, filename, pipeline):
        self.prefix = Name(prefix)
        self.filename = filename
        self.pipeline = pipeline
        self.nextSegment = 0
        self.outstanding = dict()
        self.isDone = False
        self.img = ''

        self.face = Face("127.0.0.1")



    def run(self):
        try:
            while self.nextSegment < self.pipeline:
                self._sendNextInterest(self.prefix)
                self.nextSegment += 1

            while not self.isDone:
                self.face.processEvents()
                time.sleep(0.01)

            print "quit"

        except RuntimeError as e:
            print "ERROR: %s" %  e


    def _sendNextInterest(self, name):
        nameWithSegment = Name(name).appendSegment(self.nextSegment)
        self._sendNextInterestWithSegment(nameWithSegment)


    def _sendNextInterestWithSegment(self, name):
        interest = Interest(name)
        uri = name.toUri()

        interest.setInterestLifetimeMilliseconds(4000)
        interest.setMustBeFresh(True)

        if uri not in self.outstanding:
            self.outstanding[uri] = 1

        self.face.expressInterest(interest, self._onData, self._onTimeout)
        print "Sent Interest for %s" % uri


    def _onData(self, interest, data):
        payload = data.getContent()
        dataName = data.getName()
        self.img+= str(payload)

        print "Received data: "
        del self.outstanding[interest.getName().toUri()]

        finalBlockId = data.getMetaInfo().getFinalBlockID()

        if finalBlockId.getValue().size() > 0 and \
           finalBlockId == dataName[-1]:
            self.isDone = True
            f = open(self.filename,'wb')
            f.write(self.img)
            # imgdata = numpy.fromstring(self.img, dtype='uint8')
            # decimg = cv2.imdecode(imgdata,1)
            # cv2.imshow('IMAGE',decimg)
            # cv2.waitKey(0)
            # cv2.destroyAllWindows()
        else:
            self._sendNextInterest(self.prefix)
            self.nextSegment += 1


    def _onTimeout(self, interest):
        name = interest.getName()
        uri = name.toUri()

        print "TIMEOUT #%d: segment #%s" % (self.outstanding[uri], name[-1].toNumber())
        self.outstanding[uri] += 1

        if self.outstanding[uri] <= 3:
            self._sendNextInterestWithSegment(name)
        else:
            self.isDone = True



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parse command line args for ndn consumer')

    parser.add_argument("-u", "--uri", required=True, help='ndn URI to retrieve')
    parser.add_argument("-f", "--filename", required=True, help='Received file name')
    parser.add_argument("-p", "--pipe",required=False, help='number of Interests to pipeline, default = 1', nargs= '?', const=1, type=int, default=1)

    args = parser.parse_args()

    try:
        uri = args.uri
        filename = args.filename
        pipeline = args.pipe

        Consumer(uri, filename, pipeline).run()

    except:
        traceback.print_exc(file=sys.stdout)
        print "Error parsing command line arguments"
        sys.exit(1)
