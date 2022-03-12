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
# SendBase is from 0 to the length of packets, without mod 32
sendBase = 0
nextPacketId = 0
# Initial windowsize: 1
windowSize = 1
done = False
timerList = []
timeout = 0.100
timestamp = 0
retransList = []
ackList = []
packetLen = 0

# Logs
seqnumLog = []
ackLog = []
NLog = []

# Classes
class PacketTimer:
    def __init__(self, _id):
        # id indicates the packet index of all file packets.
        # seqnum indicates the seqnum carried by a packet.
        self._id = _id
        self.seqnum = _id % 32
        self.timeBase = time.time()

    def isTimeout(self):
        res = (time.time() - self.timeBase) > timeout
        return res

    def reset(self):
        self.timeBase = time.time()


def transmission(packets, address, port, senderSocket):
    global nextPacketId
    global windowSize
    global timestamp
    global timerList
    global retransList
    global packetLen

    # Start a new thread to receive sacks
    recvThread = threading.Thread(target=recvSACK, args=(senderSocket,))
    recvThread.start()

    while not done:
        lock.acquire()
        # Step 1: CheckTimeout
        for index in range(len(timerList)):
            cur = timerList[index]
            _id = cur._id
            seqnum = cur.seqnum
            if cur.isTimeout():
                windowSize = 1
                del timerList[index]
                # Sendbase Packet timeout: Retransmit sendbase packet Immediately.
                if seqnum == sendBase % 32:
                    senderSocket.sendto(
                        packets[_id].encode(), (address, port))
                    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
                    seqnumLog.append("t=" + str(timestamp) + ' ' + str(seqnum))
                    timerList.append(PacketTimer(_id))
                    timestamp += 1
                    break
                # Other packets timeout: Add the Packet to retransList.
                else:
                    retransList.append((packets[_id], _id))
                    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
                    timestamp += 1
                    break

        # Step 2 : Check retransmission list, if we find a packet in the window, then retransmit this packet
        if len(retransList) > 0:
            deleteTargets = []
            for index in range(len(retransList)):
                # item in retransList: (packert, _id)
                cur = retransList[index][0]
                # Out of the window
                if cur.seqnum > (sendBase % 32) + windowSize:
                    continue
                # In the window
                else:
                    senderSocket.sendto(
                        cur.encode(), (address, port))
                    seqnumLog.append("t=" + str(timestamp) +
                                     ' ' + str(cur.seqnum))
                    timerList.append(PacketTimer(retransList[index][1]))
                    timestamp += 1
                    deleteTargets.append(retransList[index])
            for target in deleteTargets:
                retransList.remove(target)
        lock.release()

        # Step 3: If window is not full, try to send packets
        if nextPacketId <= min(sendBase + windowSize - 1, packetLen - 1):
            # EOT Packet: Never discard
            if(nextPacketId == packetLen - 1 and (sendBase == packetLen - 1)):
                seqnumLog.append("t=" + str(timestamp) + ' ' +
                                 'EOT')
                senderSocket.sendto(
                    packets[nextPacketId].encode(), (address, port))
                break
            # Data Packet: May be discarded, so add a timer
            elif(nextPacketId < packetLen - 1):
                senderSocket.sendto(
                    packets[nextPacketId].encode(), (address, port))
                timerList.append(PacketTimer(nextPacketId))
                seqnumLog.append("t=" + str(timestamp) + ' ' +
                                 str(packets[nextPacketId].seqnum))
                nextPacketId += 1
                timestamp += 1


def recvSACK(senderSocket):
    global sendBase
    global done
    global windowSize
    global timestamp
    global timerList

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
        # Step3: Check whether this ack is a new ack(In the ackList) and process it.
        if ackSeqnum not in ackList:
            lock.acquire()
            # Increase window size if it's a new ACK.
            if windowSize < MAX_WINDOW_SIZE:
                windowSize += 1
            NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
            ackLog.append("t=" + str(timestamp) + ' ' + str(ackSeqnum))
            # Update ackList, add the new ack to it
            if sendBase % 32 >= 23:
                if (sendBase % 32 <= ackSeqnum and ackSeqnum <= 31) or ackSeqnum <= ((sendBase + MAX_WINDOW_SIZE - 1) % 32):
                    ackList.append(ackSeqnum)
            else:
                if ackSeqnum >= sendBase % 32 and ackSeqnum <= (sendBase + MAX_WINDOW_SIZE - 1) % 32:
                    ackList.append(ackSeqnum)

            # When receive a new ack, clear the corresponding item in timerlist and the retranslist
            deleteList = []
            for index in range(len(timerList)):
                if timerList[index].seqnum == ackSeqnum:
                    deleteList.append(timerList[index])
            for item in deleteList:
                timerList.remove(item)

            # Move sendBase and then update acklist
            if(ackSeqnum == sendBase % 32):
                while (sendBase % 32) in ackList:
                    ackList.remove(sendBase % 32)
                    sendBase = min(sendBase + 1, packetLen - 1)
                    deleteList = []
                    for index in range(len(timerList)):
                        if timerList[index]._id < sendBase:
                            deleteList.append(timerList[index])
                    for item in deleteList:
                        timerList.remove(item)
            timestamp += 1
            lock.release()


def fileToPacket(filename):
    packets = []
    file = open(filename).read()

    # all data packets + 1 EOT packet
    NUM_OF_PACKETS = math.ceil(len(file) / MAX_PACKET_SIZE) + 1

    for i in range(0, NUM_OF_PACKETS - 1):
        data = file[i *
                    MAX_PACKET_SIZE:min((i + 1) * MAX_PACKET_SIZE, len(file))]
        # type seqnum lenth data (0:sack, 1: data, 2:eot)
        packets.append(Packet(1, i % 32, len(str(data)), str(data)))
    # last packet is the EOT packet
    packets.append(Packet(2, (NUM_OF_PACKETS - 1) % 32, 0, ''))
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
    global packetLen

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
    packets = fileToPacket(filename)
    packetLen = len(packets)

    # Initialize window size and create Log
    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
    timestamp += 1

    # Initialize Sockets
    senderSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    senderSocket.bind(('', sackPort))

    # Start
    transmission(packets, address, port, senderSocket)
    exportLog()


if __name__ == '__main__':
    main()
