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
sendBase = 0
nextPacketId = 0
windowSize = 1
done = False
timerList = []
timeout = 0.100
timestamp = 0
retransList = []
ackList = []
packetLen = 0

# Classes


class PacketTimer:
    def __init__(self, _id):
        self._id = _id
        self.seqnum = _id % 32
        self.timeBase = time.time()

    def isTimeout(self):
        res = (time.time() - self.timeBase) > timeout
        return res

    def reset(self):
        self.timeBase = time.time()


# Logs
seqnumLog = []
ackLog = []
NLog = []


def transmission(packets, emulatorAddr, emulatorPort, client_udp_sock):
    global nextPacketId
    global windowSize
    global timestamp
    global timerList
    global retransList

    recvThread = threading.Thread(target=recvSACK, args=(client_udp_sock,))
    recvThread.start()

    while not done:
        lock.acquire()
        for index in range(len(timerList)):
            cur = timerList[index]
            _id = cur._id
            seqnum = cur.seqnum
            if cur.isTimeout():
                windowSize = 1
                del timerList[index]
                # Sendbase Packet timeout
                if seqnum == sendBase % 32:
                    print("Sendbase Retrans", sendBase %
                          32, "current _id", _id)
                    client_udp_sock.sendto(
                        packets[_id].encode(), (emulatorAddr, emulatorPort))
                    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
                    seqnumLog.append("t=" + str(timestamp) + ' ' + str(seqnum))
                    timerList.append(PacketTimer(_id))
                    timestamp += 1
                    break
                else:
                    retransList.append((packets[_id], _id))
                    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
                    timestamp += 1
                    break
        # lock.release()

        # process retran
        # lock.acquire()
        if len(retransList) > 0:
            deleteTargets = []
            for index in range(len(retransList)):
                # item in retransList: (packert, _id)
                cur = retransList[index][0]
                if cur.seqnum > (sendBase % 32) + windowSize:
                    continue
                else:
                    print("Normal Retrans", retransList[index][1])
                    client_udp_sock.sendto(
                        cur.encode(), (emulatorAddr, emulatorPort))
                    seqnumLog.append("t=" + str(timestamp) +
                                     ' ' + str(cur.seqnum))
                    timerList.append(PacketTimer(retransList[index][1]))
                    timestamp += 1
                    deleteTargets.append(retransList[index])
                    # del retransList[index]
            for target in deleteTargets:
                retransList.remove(target)
        # lock.release()

        # if window is not full, send segments
        if nextPacketId <= min(sendBase + windowSize - 1, len(packets) - 1):
            # lock.acquire()
            client_udp_sock.sendto(
                packets[nextPacketId].encode(), (emulatorAddr, emulatorPort))
            # EOT Packet: Never discard
            if(nextPacketId == len(packets) - 1):
                seqnumLog.append("t=" + str(timestamp) + ' ' +
                                 'EOT')
            # Data Packet: May be discarded, add a timer
            else:
                timerList.append(PacketTimer(nextPacketId))
                seqnumLog.append("t=" + str(timestamp) + ' ' +
                                 str(packets[nextPacketId].seqnum))
            nextPacketId += 1
            timestamp += 1
            # lock.release()
        lock.release()


def recvSACK(client_udp_sock):
    global sendBase
    global done
    global windowSize
    global timestamp
    global timerList

    while not done:
        # lock.acquire()
        msg, _ = client_udp_sock.recvfrom(4096)
        sack_packet = Packet(msg)
        sack_seqnum = sack_packet.seqnum
        sack_type = sack_packet.typ
        print("recv ack", sack_seqnum)

        # if received an ack for EOT, exit
        if sack_type == 2:
            lock.acquire()
            done = True
            ackLog.append("t=" + str(timestamp) + ' ' + 'EOT')
            lock.release()
            break
        # New ack
        if sack_seqnum not in ackList:
            lock.acquire()
            if windowSize < 10:
                windowSize += 1
            NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
            ackLog.append("t=" + str(timestamp) + ' ' + str(sack_seqnum))
            ackList.append(sack_seqnum)
            for index in range(len(timerList)):
                if timerList[index].seqnum == sack_seqnum:
                    del timerList[index]
                    break

            # Send
            if(sack_seqnum == sendBase % 32):
                while (sendBase % 32) in ackList:
                    print("Send Base:", sendBase)
                    ackList.remove(sendBase % 32)
                    sendBase = min(sendBase + 1, packetLen -1)
                    print("Send Base + 1:", sendBase)
            timestamp += 1
            lock.release()
        # lock.release()


def fileToPacket(filename):
    packets = []
    file = open(filename, "rb").read().decode()

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


def writeLogFile():
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

    # time.log
    file = open('N.log', 'w+')
    for log in NLog:
        file.write(str(log) + "\n")
    file.close()


def main():
    global timeout
    global timestamp
    global packetLen

    if len(sys.argv) != 6:
        print("Improper number of arguments")
        exit(1)

    emulatorAddr = sys.argv[1]
    emulatorPort = int(sys.argv[2])
    sackPort = int(sys.argv[3])
    timeout = float(sys.argv[4]) / 1000
    filename = sys.argv[5]

    packets = fileToPacket(filename)
    packetLen = len(packets)
    # Initialize window size
    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
    timestamp += 1

    client_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_udp_sock.bind(('', sackPort))

    transmission(packets, emulatorAddr, emulatorPort, client_udp_sock)
    writeLogFile()


if __name__ == '__main__':
    main()
