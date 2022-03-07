import sys
import socket
from packet import Packet

SEQ_MODULO = 32

arrival_log = []
expected_pkt_num = 0
packet_buffer = {}
hasBufferedEOT = False
EOTSeqnum = -1
done = False


def receive(file, emulatorAddr, emuReceiveACK, client_udp_sock):
    global done
    while not done:
        global expected_pkt_num
        global packet_buffer
        global hasBufferedEOT
        global EOTSeqnum

        # If we have received the EOT Packet and has already have all data packets, send EOT back
        if hasBufferedEOT and (expected_pkt_num == EOTSeqnum):
            EOT = Packet(2, seq_num, 0, '')
            print("Send EOT Packet")
            client_udp_sock.sendto(EOT.encode(), (emulatorAddr, emuReceiveACK))
            done = True
            break

        msg, _ = client_udp_sock.recvfrom(4096)
        data_packet = Packet(msg)
        packet_type = data_packet.typ
        seq_num = data_packet.seqnum
        data = data_packet.data
        if packet_type == 1:
            arrival_log.append(seq_num)
        elif packet_type == 2:
            arrival_log.append('EOT')
        print("recv seqnum =>", seq_num)
        print("current expect num", expected_pkt_num)

        # receives EOT, send EOT back and exit
        if packet_type == 2:
            hasBufferedEOT = True
            EOTSeqnum = seq_num
            print("BUffer EOT", hasBufferedEOT, "SEQ",
                  EOTSeqnum, "expect", expected_pkt_num)

        # receives expected data packet
        if packet_type == 1:
            client_udp_sock.sendto(
                Packet(0, seq_num, 0, '').encode(), (emulatorAddr, emuReceiveACK))
            # Buffer packet
            if expected_pkt_num >= 23:
                if (expected_pkt_num <= seq_num and seq_num <= 31) or seq_num <= ((expected_pkt_num + 9) % SEQ_MODULO):
                    packet_buffer[seq_num] = data
            else:
                if seq_num >= expected_pkt_num and seq_num <= expected_pkt_num + 9:
                    packet_buffer[seq_num] = data
            # if (seq_num >= expected_pkt_num and seq_num <= expected_pkt_num + 9) or (expected_pkt_num > 22 and seq_num <= ((expected_pkt_num + 9) % SEQ_MODULO)):
            #     packet_buffer[seq_num] = data

            while expected_pkt_num in packet_buffer:
                file.write(packet_buffer[expected_pkt_num].encode())
                del packet_buffer[expected_pkt_num]
                expected_pkt_num = (expected_pkt_num + 1) % SEQ_MODULO
                print("Final Exp", expected_pkt_num, "EOT NUM", EOTSeqnum)

def writeLogFile():
    # Writing log file
    # arrival.log
    f = open('arrival.log', 'w+')
    for log in arrival_log:
        f.write(str(log) + "\n")
    f.close()


def main():
    if len(sys.argv) != 5:
        print("Improper number of arguments")
        exit(1)

    emulatorAddr = sys.argv[1]
    emuReceiveACK = int(sys.argv[2])
    rcvrReceiveData = int(sys.argv[3])
    filename = sys.argv[4]

    client_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_udp_sock.bind(('', rcvrReceiveData))

    try:
        file = open(filename, 'wb')
    except IOError:
        print('Unable to open', filename)
        return

    receive(file, emulatorAddr, emuReceiveACK, client_udp_sock)

    writeLogFile()

    file.close()


if __name__ == '__main__':
    main()
