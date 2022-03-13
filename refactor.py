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
        self.timerBase = None
        self.packet = packet
        self.lost = False
        self.receivedAck = False

    def startTimer(self):
        self.timerBase = time.time()
        self.hasTimer = True

    def isTimeout(self):
        res = (time.time() - self.timerBase) > timeout
        return res

    def resetTimer(self):
        self.timerBase = time.time()


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
        for index in list(range(basePointer, nextPointer)):
            cur = packets[index]
            if cur.hasTimer and not cur.receivedAck and not cur.lost:
                if cur.isTimeout():
                    packets[index].lost = True
                    lock.acquire()
                    windowSize = 1
                    windowBoundary = basePointer
                    # Sendbase packet lost
                    if cur._id == basePointer:
                        send(packets[basePointer])
                        packets[basePointer].resetTimer()
                        NLog.append("t=" + str(timestamp) +
                                    ' ' + str(windowSize))
                        seqnumLog.append(
                            "t=" + str(timestamp) + ' ' + str(cur.seqnum))
                        timestamp += 1
                        lock.release()
                        break
                    # Other packets lost
                    else:
                        # packets[index].hasTimer = False
                        NLog.append("t=" + str(timestamp) +
                                    ' ' + str(windowSize))
                        timestamp += 1
                        lock.release()
                        break

        for index in list(range(basePointer, min(windowBoundary + 1, len(packets)))):
            cur = packets[index]
            if not cur.receivedAck and (cur.lost == True or cur._id == nextPointer):
                if cur.packet.typ == 2 and basePointer == len(packets) - 1 and not EOTSended:
                    send(cur)
                    cur.startTimer()
                    seqnumLog.append("t=" + str(timestamp) +
                                     ' ' + 'EOT')
                    EOTSended = True
                    break
                elif cur.packet.typ == 1:
                    send(cur)
                    # When sending a packet that has not been sent before, move nextPointer
                    if(cur.lost == False):
                        cur.startTimer()
                        nextPointer = nextPointer + 1
                    # Retransmission packet
                    else:
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
            done = True
            ackLog.append("t=" + str(timestamp) + ' ' + 'EOT')
            break
        else:
            # Recore this ack seqnum even though it's an old ack
            ackLog.append("t=" + str(timestamp) + ' ' + str(ackSeqnum))

            # Step3: Check whether this ack is a new ack, this ack should in a reasonable range
            # Then process it.

            # Situation 1 : basePointer >= 23
            if basePointer % 32 >= 23:
                baseSeq = basePointer % 32
                if ackSeqnum >= baseSeq and packets[math.floor(basePointer / 32) * 32 + ackSeqnum].receivedAck == False:
                    cur = packets[math.floor(
                        basePointer / 32) * 32 + ackSeqnum]
                    cur.receivedAck = True
                    if windowSize < 10:
                        lock.acquire()
                        windowSize += 1
                        lock.release()
                    NLog.append("t=" + str(timestamp) +
                                ' ' + str(windowSize))
                    windowBoundary = basePointer + windowSize - 1
                    timestamp += 1
                elif ackSeqnum <= (baseSeq + MAX_WINDOW_SIZE - 1) % 32 and packets[(math.floor(basePointer / 32) + 1) * 32 + ackSeqnum].receivedAck == False:
                    cur = packets[(math.floor(
                        basePointer / 32) + 1) * 32 + ackSeqnum]
                    cur.receivedAck = True
                    if windowSize < 10:
                        lock.acquire()
                        windowSize += 1
                        lock.release()
                    NLog.append("t=" + str(timestamp) +
                                ' ' + str(windowSize))
                    windowBoundary = basePointer + windowSize - 1
                    timestamp += 1

            # Situation 2 : basePointer < 23
            else:
                baseSeq = basePointer % 32

                if ackSeqnum >= (baseSeq + MAX_WINDOW_SIZE - 1) and packets[((math.floor(basePointer / 32) - 1) * 32) + ackSeqnum].receivedAck == False:
                    cur = packets[(math.floor(
                        basePointer / 32 - 1)) * 32 + ackSeqnum]
                    cur.receivedAck = True
                    if windowSize < 10:
                        lock.acquire()
                        windowSize += 1
                        lock.release()
                    NLog.append("t=" + str(timestamp) +
                                ' ' + str(windowSize))
                    windowBoundary = basePointer + windowSize - 1
                    timestamp += 1
                elif ackSeqnum <= baseSeq and packets[math.floor(basePointer / 32) * 32 + ackSeqnum].receivedAck == False:
                    cur = packets[math.floor(
                        basePointer / 32) * 32 + ackSeqnum]
                    cur.receivedAck = True
                    if windowSize < 10:
                        lock.acquire()
                        windowSize += 1
                        lock.release()
                    NLog.append("t=" + str(timestamp) +
                                ' ' + str(windowSize))
                    windowBoundary = basePointer + windowSize - 1
                    timestamp += 1

            # Step 4: Move basePointer
            lock.acquire()
            while packets[basePointer].receivedAck == True:
                basePointer += 1
                windowBoundary = min(
                    basePointer + windowSize - 1, len(packets))
                if basePointer == len(packets):
                    windowBoundary = len(packets)
            lock.release()


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
