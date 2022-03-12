import sys
import socket
from packet import Packet

arrivalLog = []
expectedNum = 0
packetBuffer = {}
done = False


def receive(file, address, port, receiverSocket):
    global done
    while not done:
        global expectedNum
        global packetBuffer

        # Get packets from sender
        res, _ = receiverSocket.recvfrom(4096)
        receivedPacket = Packet(res)
        packetType = receivedPacket.typ
        packetNum = receivedPacket.seqnum
        data = receivedPacket.data
        # Log
        if packetType == 1:
            arrivalLog.append(packetNum)
        elif packetType == 2:
            arrivalLog.append('EOT')
        print("recv seqnum =>", packetNum)
        print("current expect num", expectedNum)

        # receives EOT, send EOT back and exit
        if packetType == 2:
            EOT = Packet(2, packetNum, 0, '')
            print("Send EOT Packet")
            receiverSocket.sendto(EOT.encode(), (address, port))
            done = True

        # receives expected data packet
        if packetType == 1:
            receiverSocket.sendto(
                Packet(0, packetNum, 0, '').encode(), (address, port))
            # Buffer packet
            if expectedNum >= 23:
                if (expectedNum <= packetNum and packetNum <= 31) or packetNum <= ((expectedNum + 9) % 32):
                    packetBuffer[packetNum] = data
            else:
                if packetNum >= expectedNum and packetNum <= expectedNum + 9:
                    packetBuffer[packetNum] = data

            while expectedNum in packetBuffer:
                file.write(packetBuffer[expectedNum].encode())
                del packetBuffer[expectedNum]
                expectedNum = (expectedNum + 1) % 32


def exportLog():
    f = open('arrival.log', 'w+')
    for log in arrivalLog:
        f.write(str(log) + "\n")
    f.close()


def main():
    # Validate arguments
    if len(sys.argv) != 5:
        print("Improper number of arguments")
        exit(1)

    # Initialize variables
    address = sys.argv[1]
    port = int(sys.argv[2])
    receivePort = int(sys.argv[3])
    filename = sys.argv[4]
    receiverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiverSocket.bind(('', receivePort))

    # Log file
    try:
        file = open(filename, 'wb')
    except IOError:
        print('Unable to open', filename)
        return

    # Run receiver
    receive(file, address, port, receiverSocket)

    # Export log file
    exportLog()

    file.close()


if __name__ == '__main__':
    main()
