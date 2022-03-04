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
nextSeqnum = 0
windowSize = 1
done = False
timerList = []
timeout = 0.100
timestamp = 0
retransList = []
ackList = []

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
    global nextSeqnum
    global windowSize
    global timestamp
    global timerList

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
                if index == sendBase:
                    print("Sendbase Retrans", sendBase)
                    client_udp_sock.sendto(
                        packets[_id].encode(), (emulatorAddr, emulatorPort))
                    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
                    seqnumLog.append("t=" + str(timestamp) + ' ' + str(seqnum))
                    timerList.append(PacketTimer(_id))
                    timestamp += 1
                    break
                else:
                    retransList.append(packets[_id])
                    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
                    timestamp += 1
                    break
        lock.release()

        if len(retransList) > 0:
            for index in range(len(retransList)):
                cur = retransList[index]
                if cur.seqnum > sendBase + windowSize:
                    break
                else:
                    lock.acquire()
                    print("Normal Retrans", _id)
                    client_udp_sock.sendto(
                        retransList[index].encode(), (emulatorAddr, emulatorPort))
                    seqnumLog.append("t=" + str(timestamp) +
                                     ' ' + str(sendBase))
                    timerList.append(PacketTimer(_id))
                    timestamp += 1
                    del retransList[index]
                    lock.release()
        # if window is not full, send segments
        if nextSeqnum < min(sendBase + windowSize, len(packets)):
            client_udp_sock.sendto(
                packets[nextSeqnum].encode(), (emulatorAddr, emulatorPort))
            lock.acquire()
            timerList.append(PacketTimer(nextSeqnum))
            seqnumLog.append(packets[nextSeqnum].seqnum)
            nextSeqnum += 1
            timestamp += 1
            lock.release()


def recvSACK(client_udp_sock):
    print("recv")
    global sendBase
    global done
    global windowSize
    global timestamp
    global timerList

    while not done:
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
            windowSize += 1
            NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))
            ackLog.append("t=" + str(timestamp) + ' ' + str(sack_seqnum))
            ackList.append(sack_seqnum)
            for index in range(len(timerList)):
                if timerList[index].seqnum == sack_seqnum:
                    del timerList[index]
                    break

            if(sack_seqnum == sendBase):
                while sendBase in ackList:
                    ackList.remove(sendBase)
                    sendBase += 1
            timestamp += 1
            lock.release()


def fileToPacket(filename):
    packets = []
    file = open(filename, "rb").read().decode()

    # all data packets + 1 EOT packet
    NUM_OF_PACKETS = math.ceil(len(file) / MAX_PACKET_SIZE) + 1

    for i in range(0, NUM_OF_PACKETS - 1):
        data = file[i *
                    MAX_PACKET_SIZE:min((i + 1) * MAX_PACKET_SIZE, len(file))]
        # type seqnum lenth data (0:sack, 1: data, 2:eot)
        packets.append(Packet(1, i, len(str(data)), str(data)))
    # last packet is the EOT packet
    packets.append(Packet(2, NUM_OF_PACKETS, 0, ''))
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

    if len(sys.argv) != 6:
        print("Improper number of arguments")
        exit(1)

    print(sys.argv)
    emulatorAddr = sys.argv[1]
    emulatorPort = int(sys.argv[2])
    sackPort = int(sys.argv[3])
    timeout = float(sys.argv[4]) / 1000
    filename = sys.argv[5]

    packets = fileToPacket(filename)
    # Initialize window size
    NLog.append("t=" + str(timestamp) + ' ' + str(windowSize))

    client_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_udp_sock.bind(('', sackPort))

    transmission(packets, emulatorAddr, emulatorPort, client_udp_sock)
    writeLogFile()


if __name__ == '__main__':
    main()
