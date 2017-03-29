import config
import os
import socket
import ssl
import struct
import time
import traceback
import Logger

def tohex(s):
    '''Convert string of 8-bit characters into 2 hex digits each
    '''
    return ":".join("{:02x}".format(ord(c)) for c in s)

def fromhex(s):
    '''Convert string of hex digits into an 8-bit character string.
    '''
    return ''.join([chr(int(''.join(c), 16)) for c in zip(s[0::2],s[1::2])])

class PushRequest(object):
    def __init__(self, identifier, msg):
        self.identifier = identifier
        self.msg = msg
        self.when = time.time()
        self.attempts = 0

class APNs(object):

    host = ['gateway.push.apple.com', 'gateway.sandbox.push.apple.com'][config.useSandbox]
    port = 2195

    kErrors = {
        0: "No error",
        1: "Processing error",
        2: "Missing device token",
        3: "Missing topic",
        4: "Missing payload",
        5: "Invalid token size",
        6: "Invalid topic size",
        7: "Invalid payload size",
        8: "Invalid token",
        10: "Shutdown",
        128: "Protocol error",
        255: "Unknown"
    }

    def __init__(self):
        self.__service = None
        self.__identifier = 1
        self.__whenLastPost = 0
        self.__history = []
        self.__pending = []

    def generatePayload(self, msg, badge):
        return config.payloadTemplate.format(msg, badge)

    def connect(self):
        gLog.info('connect')

        # Create underlying TCP socket to use for notification transport to Apple
        #
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)

        # Turn off any Nagel algorithm buffering. Use TCP keepalive packets.
        #
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.settimeout(config.socketReadTimeout)

        pwd = os.getcwd()
        self.__service = ssl.wrap_socket(sock, 
                                         keyfile = os.path.join(pwd, config.apnsKeyFile ),
                                         certfile = os.path.join(pwd, config.apnsCertFile),
                                         ssl_version = ssl.PROTOCOL_TLSv1)

        try:
            self.__service.connect((self.host, self.port))
            gLog.info('connected to', self.host, self.port)
        except:
            traceback.print_exc()
            gLog.error('failed to connect to', self.host, self.port)
            self.__service = None

    def close(self):
        if self.__service:
            try:
                self.__service.close()
            except:
                pass
            self.__service = None

    def post(self, deviceToken, msg, badge, expiry = 0):
        gLog.begin()

        deviceToken = fromhex(deviceToken)
        if len(deviceToken) != 32:
            gLog.error('invalid device token')
            gLog.end(False)
            return False

        payload = self.generatePayload(msg, badge)

        size = len(payload)
        gLog.debug('payload size:', size)
        gLog.debug('payload:', payload)

        # Item 1 - device token (1 byte + 2 bytes + 32 bytes = 35)
        #
        frameItem = struct.pack('!BH', 1, 32) + deviceToken
        gLog.debug(1, tohex(frameItem))
        frame = frameItem

        # Item 2 - notification payload (1 byte + 2 bytes + N = 3 + N)
        #
        frameItem = struct.pack('!BH', 2, len(payload)) + payload
        gLog.debug(2, tohex(frameItem))
        frame += frameItem

        # Item 3 - notification identifier (1 byte + 2 bytes + 4 bytes = 7)
        #
        identifier = self.__identifier
        self.__identifier += 1
        frameItem = struct.pack('!BHI', 3, 4, identifier)
        gLog.debug(3, tohex(frameItem))
        frame += frameItem

        if expiry > 0:
            
            # Item 4 - expiration date (1 byte + 2 bytes + 4 bytes = 7)
            #
            expiry = socket.htonl(int(time.time()) + expiry)
            frameItem = struct.pack('!BHI', 4, 4, expiry)
            gLog.debug(4, tohex(frameItem))

        # Item 5 - priority (1 byte + 2 bytes + 1 byte = 4)
        #
        priority = 10           # send immediately
        frameItem = struct.pack('!BHB', 5, 1, priority)
        gLog.debug(5, tohex(frameItem))
        frame += frameItem

        # Frame (1 byte + 2 bytes + len(frame) = 3 + len)
        #
        msg = struct.pack('!BI', 2, len(frame)) + frame
        gLog.debug(tohex(msg))

        self.__pending.append(PushRequest(identifier, msg))
        self.processPending()
        self.pruneHistory()

    kRetry = 1
    kOK = 2
    kFailure = 3

    def processPending(self):

        # If the socket is too old, recycle it.
        #
        age = time.time() - self.__whenLastPost
        gLog.debug('age:', age)
        if self.__service != None and age > config.socketAgeLimit:
            gLog.warning('recycling existing APNs connection - age:', age)
            self.close()

        while len(self.__pending) > 0:

            if self.__service == None:
                self.connect()

            request = self.__pending[0]
            if request.attempts < config.maxPostRetries:
                rc = self.processOne(request)
                if rc == self.kRetry:
                    continue
            del self.__pending[0]

    def processOne(self, request):
        gLog.begin()

        # Try writing to the socket. If we fail, retry.
        #
        try:
            request.attempts += 1
            rc = self.__service.write(request.msg)
            gLog.debug('sent:', rc)
            if rc != len(request.msg):
                raise RuntimeError('write failed')
        except:
            traceback.print_exc()
            self.close()
            return self.kRetry

        self.__history.append(request)
        self.__whenLastPost = time.time()

        # Try fetching from the socket. If there is anything, then something went wrong.
        # TODO: move to async IO and make this into a separate thread.
        #
        try:
            raw = self.__service.recv(6)
            if raw != None and len(raw) == 6:
                command, status, identifier = struct.unpack('!BBI', raw)
                gLog.debug(command, status, identifier)
                if command != 8:
                    gLog.error('unknown response command from APNs:', command)
                else:
                    gLog.error('error from APNs:', status, self.kErrors.get(status))

                # Locate the first historical request that has an identifier greater than what APNs returned.
                # We need to resend requests from that point in the history.
                #
                for index, request in enumerate(self.__history):
                    if request.identifier > identifier:
                        redo = self.__history[index:]
                        for each in redo:
                            redo.attempts = 0
                        self.__pending = redo + self.__pending
                        self.__history = []
                        break

                # Regardless of status code, the socket is no longer usable.
                #
                self.close()

                # If Apple closed the socket for some maintenance reason, try again with a new connection
                #
                if status == 10:
                    return self.kRetry

                return self.kFailure

        except ssl.SSLError:

            # Timeout error - no news is good news
            #
            gLog.info("OK - no response from APNs")

        return self.kOK

    def pruneHistory(self):

        # Find the first entry that is not stale and make that the first entry in the history
        #
        now = time.time()
        for index, request in enumerate(self.__history):
            if now - request.when < config.historyAgeLimit:
                self.__history = self.__history[index:]
                break
