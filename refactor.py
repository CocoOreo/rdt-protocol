import sys
import socket
import threading
import time
from packet import Packet
import math

# Global configs
MAX_WINDOW_SIZE = 10
MAX_PACKET_SIZE = 500

# Global variables
lock = threading.Lock()
basePointer = 0
nextPointer = 0
windowBoundary = 0
windowSize = 1
timestamp = 0
senderSocket = None
address = ''
port = 0
filename = ''
EOTSended = False
done = False
packets = []

# Logs
seqnumLog = []
ackLog = []
NLog = []

# Classes


class PacketWithTimer:
    def __init__(self, _id, packet):
        # id indicates the packet index of all file packets.
        # seqnum indicates the seqnum carried by a packet.
        self._id = _id
        self.seqnum = _id % 32
        self.hasTimer = False
        self.timeBase = None
        self.packet = packet
        self.lost = False
        self.receivedAck = False

    def startTimer(self):
        self.timerBase = time.time()
        self.hasTimer = True

    def isTimeout(self):
        res = (time.time() - self.timeBase) > timeout
        return res

    def resetTimer(self):
        self.timeBase = time.time()


def send(timerPacket):
    data = timerPacket.packet
    senderSocket.sendto(data.encode(), (address, port))


def transmission():
    global nextPointer
    global basePointer
    global windowBoundary
    global windowSize
    global timestamp
    global EOTSended
    global packets
    global done

    # Start a new thread to receive sacks
    recvThread = threading.Thread(target=recvSACK, args=(senderSocket,))
    recvThread.start()

    while not done:
        # Step CheckTimerout
        lock.acquire()
        for index in list(range(basePointer, nextPointer)):
            cur = packets[index]
            if cur.hasTimer and not cur.receivedAck:
                if cur.isTimeout():
                    packets[index].lost = True
                    windowSize = 1
                    windowBoundary = basePointer
                    # Sendbase packet lost
                    if cur._id == basePointer:
                        send(packets[basePointer])
                        NLog.append("t=" + str(timestamp) +
                                    ' ' + str(windowSize))
                        seqnumLog.append(
                            "t=" + str(timestamp) + ' ' + str(cur.seqnum))
                        timestamp += 1
                    # Other packets lost
                    else:
                        NLog.append("t=" + str(timestamp) +
                                    ' ' + str(windowSize))
                        timestamp += 1
                        break
        lock.release()

        for index in list(range(basePointer, windowBoundary + 1)):
            cur = packets[index]
            if not cur.receivedAck and (cur.lost == True or cur._id == nextPointer):
                if cur.packet.typ == 2 and basePointer == len(packets) - 1 and not EOTSended:
                    send(cur)
                    seqnumLog.append("t=" + str(timestamp) +
                                     ' ' + 'EOT')
                    EOTSended = True
                    break
                else:
                    send(cur)
                    # When sending a packet that has not been sent before, move nextPointer
                    if(cur.lost == False):
                        nextPointer = nextPointer + 1
                    cur.resetTimer()
                    cur.lost = False
                    seqnumLog.append("t=" + str(timestamp) +
                                     ' ' + str(cur.seqnum))

                    timestamp += 1


def recvSACK(senderSocket):
    global basePointer
    global windowBoundary
    global nextPointer
    global timestamp
    global packets
    global windowSize
    global done

    while not done:
        # Step 1: Waiting for SACK packets
        data, _ = senderSocket.recvfrom(4096)
        ackPacket = Packet(data)
        ackSeqnum = ackPacket.seqnum
        ackType = ackPacket.typ
        print("recv ack", ackSeqnum)

        # Step 2: Check EOT, If received an ack for EOT, then exit.
        if ackType == 2:
            lock.acquire()
            done = True
            ackLog.append("t=" + str(timestamp) + ' ' + 'EOT')
            lock.release()
            break
        else:
            # Recore this ack seqnum even though it's an old ack
            ackLog.append("t=" + str(timestamp) + ' ' + str(ackSeqnum))

            # Step3: Check whether this ack is a new ack, this ack should in a reasonable range
            # Then process it.
            if packets[math.floor(basePointer / 32) * 32 + ackSeqnum].receivedAck == False:
                if basePointer % 32 >= 23:
                    if (basePointer % 32 <= ackSeqnum and ackSeqnum <= 31) or ackSeqnum <= ((basePointer + MAX_WINDOW_SIZE - 1) % 32):
                        cur = packets[math.floor(
                            basePointer / 32) * 32 + ackSeqnum]
                else:
                    if ackSeqnum >= basePointer % 32 and ackSeqnum <= (basePointer + MAX_WINDOW_SIZE - 1) % 32:
                        cur = packets[math.floor(
                            basePointer / 32) * 32 + ackSeqnum]
                cur.receivedAck = True
                if windowSize < 10:
                    windowSize += 1
                NLog.append("t=" + str(timestamp) +
                                ' ' + str(windowSize))
                windowBoundary = basePointer + windowSize - 1

            # Step 4: Move basePointer
            while packets[basePointer].receivedAck == True:
                basePointer += 1
                windowBoundary = min(
                    basePointer + windowSize - 1, len(packets) - 1)
            timestamp += 1


def convertPacket(filename):
    packets = []
    file = open(filename).read()

    # all data packets + 1 EOT packet
    NUM_OF_PACKETS = math.ceil(len(file) / MAX_PACKET_SIZE) + 1

    for i in range(0, NUM_OF_PACKETS - 1):
        data = file[i *
                    MAX_PACKET_SIZE:min((i + 1) * MAX_PACKET_SIZE, len(file))]
        # type seqnum lenth data (0:sack, 1: data, 2:eot)
        packets.append(PacketWithTimer(i, Packet(1, i %
                       32, len(str(data)), str(data))))
    # last packet is the EOT packet
    packets.append(PacketWithTimer(NUM_OF_PACKETS - 1,
                   Packet(2, (NUM_OF_PACKETS - 1) % 32, 0, '')))
    return packets


def exportLog():
    # seqnum.log
    file = open('seqnum.log', 'w+')
    for log in seqnumLog:
        file.write(str(log) + "\n")
    file.close()

    # ack.log
    file = open('ack.log', 'w+')
    for log in ackLog:
        file.write(str(log) + "\n")
    file.close()

    # N.log
    file = open('N.log', 'w+')
    for log in NLog:
        file.write(str(log) + "\n")
    file.close()


def main():
    global timeout
    global timestamp
    global senderSocket
    global address
    global port
    global sackPort
    global filename
    global packets

    # Validate parameters
    if len(sys.argv) != 6:
        print("Improper number of arguments")
        exit(1)

    address = sys.argv[1]
    port = int(sys.argv[2])
    sackPort = int(sys.argv[3])
    timeout = float(sys.argv[4]) / 1000
    filename = sys.argv[5]

    # Divide a file into packets
    packets = convertPacket(filename)

    # Initialize window size and create Log
    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
    timestamp += 1

    # Initialize Sockets
    senderSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    senderSocket.bind(('', sackPort))

    # Start
    transmission()

    # Export Log file
    exportLog()


if __name__ == '__main__':
    main()
