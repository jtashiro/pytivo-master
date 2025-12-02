import logging
import re
import socket
import struct
import subprocess
import time
import uuid
from threading import Timer
from urllib.parse import quote

import zeroconf

import config
from plugin import GetPlugin

SHARE_TEMPLATE = '/TiVoConnect?Command=QueryContainer&Container=%s'
PLATFORM_MAIN = 'pyTivo'
PLATFORM_VIDEO = 'pc/pyTivo'    # For the nice icon

class ZCListener:
    def __init__(self, names):
        self.names = names

    def removeService(self, server, type, name):
        self.names.remove(name.replace('.' + type, ''))

    def addService(self, server, type, name):
        self.names.append(name.replace('.' + type, ''))

class ZCBroadcast:
    def __init__(self, logger):
        """ Announce our shares via Zeroconf. """
        self.share_names = []
        self.share_info = []
        self.logger = logger
        self.rz = zeroconf.Zeroconf()
        self.renamed = {}
        old_titles = self.scan()
        address = socket.inet_aton(config.get_ip())
        port = int(config.getPort())
        logger.info('Announcing shares...')
        for section, settings in config.getShares():
            try:
                ct = GetPlugin(settings['type']).CONTENT_TYPE
            except:
                continue
            if ct.startswith('x-container/'):
                if 'video' in ct:
                    platform = PLATFORM_VIDEO
                else:
                    platform = PLATFORM_MAIN
                logger.info('Registering: %s' % section)
                self.share_names.append(section)
                desc = {'path': SHARE_TEMPLATE % quote(section),
                        'platform': platform, 'protocol': 'http',
                        'tsn': '{%s}' % uuid.uuid4()}
                tt = ct.split('/')[1]
                
                # Append hostname to share name if configured
                title = section
                if config.getAppendHostname():
                    try:
                        hostname = subprocess.check_output(['hostname', '-s'], text=True).strip()
                    except:
                        hostname = socket.gethostname().split('.')[0]
                    title = '%s (%s)' % (section, hostname)
                    logger.info('Appending hostname to share: %s -> %s' % (section, title))
                
                count = 1
                while title in old_titles:
                    count += 1
                    if config.getAppendHostname():
                        title = '%s (%s) [%d]' % (section, hostname, count)
                    else:
                        title = '%s [%d]' % (section, count)
                    self.renamed[section] = title
                info = zeroconf.ServiceInfo('_%s._tcp.local.' % tt,
                    '%s._%s._tcp.local.' % (title, tt),
                    address, port, 0, 0, desc)
                self.rz.registerService(info)
                self.share_info.append(info)
                logger.info('Zeroconf: Registered %s._%s._tcp.local. at %s:%d' % (title, tt, socket.inet_ntoa(address), port))

    def scan(self):
        """ Look for TiVos using Zeroconf. """
        VIDS = '_tivo-videos._tcp.local.'
        names = []

        self.logger.info('Scanning for TiVos...')

        # Get the names of servers offering TiVo videos
        browser = zeroconf.ServiceBrowser(self.rz, VIDS, ZCListener(names))

        # Give them a second to respond
        time.sleep(1)

        # Any results?
        if names:
            config.tivos_found = True
            self.logger.debug('Found %d TiVo(s): %s' % (len(names), ', '.join(names)))
        else:
            self.logger.info('No TiVos found on network')

        # Now get the addresses -- this is the slow part
        for name in names:
            info = self.rz.getServiceInfo(VIDS, name + '.' + VIDS)
            if info:
                self.logger.debug('Got service info for: %s' % name)
                # Python 3: properties might be bytes, need to handle both
                # Try both 'TSN' and 'tsn' keys, and handle bytes
                tsn = info.properties.get(b'TSN') or info.properties.get('TSN')
                if config.get_server('togo_all'):
                    tsn = info.properties.get(b'tsn') or info.properties.get('tsn', tsn)
                # Decode bytes to string if needed
                if isinstance(tsn, bytes):
                    tsn = tsn.decode('utf-8')
                if tsn:
                    address = socket.inet_ntoa(info.getAddress())
                    port = info.getPort()
                    config.tivos[tsn] = {'name': name, 'address': address, 
                                         'port': port}
                    # Convert property values from bytes to strings for Python 3
                    for key, value in info.properties.items():
                        prop_key = key.decode('utf-8') if isinstance(key, bytes) else key
                        prop_value = value.decode('utf-8') if isinstance(value, bytes) else value
                        config.tivos[tsn][prop_key] = prop_value
                    self.logger.info('%s - TSN: %s, Address: %s:%d' % (name, tsn, address, port))
                    # Log additional TiVo properties
                    platform = config.tivos[tsn].get('platform', 'unknown')
                    sw_version = config.tivos[tsn].get('swversion', 'unknown')
                    self.logger.debug('  Platform: %s, Software: %s' % (platform, sw_version))
                else:
                    self.logger.debug('No TSN found for: %s' % name)
            else:
                self.logger.debug('No service info for: %s' % name)

        return names

    def shutdown(self):
        self.logger.info('Unregistering: %s' % ' '.join(self.share_names))
        for info in self.share_info:
            self.rz.unregisterService(info)
        self.rz.close()

class Beacon:
    def __init__(self):
        self.UDPSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.UDPSock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.services = []

        self.platform = PLATFORM_VIDEO
        for section, settings in config.getShares():
            try:
                ct = GetPlugin(settings['type']).CONTENT_TYPE
            except:
                continue
            if ct in ('x-container/tivo-music', 'x-container/tivo-photos'):
                self.platform = PLATFORM_MAIN
                break

        if config.get_zc():
            logger = logging.getLogger('pyTivo.beacon')
            try:
                self.bd = ZCBroadcast(logger)
            except Exception as e:
                logger.error('Zeroconf failure: %s' % str(e))
                self.bd = None
        else:
            self.bd = None

    def add_service(self, service):
        self.services.append(service)
        logger = logging.getLogger('pyTivo.beacon')
        beacon_addrs = config.getBeaconAddresses()
        logger.info('Beacon addresses: %s' % beacon_addrs)
        logger.info('Beacon service: %s' % service)
        self.send_beacon()

    def format_services(self):
        return ';'.join(self.services)

    def format_beacon(self, conntype, services=True):
        beacon = ['tivoconnect=1',
                  'method=%s' % conntype,
                  'identity={%s}' % config.getGUID(),
                  'machine=%s' % socket.gethostname(),
                  'platform=%s' % self.platform]

        if services:
            beacon.append('services=' + self.format_services())
        else:
            beacon.append('services=TiVoMediaServer:0/http')

        return '\n'.join(beacon) + '\n'

    def send_beacon(self):
        beacon_ips = config.getBeaconAddresses()
        beacon = self.format_beacon('broadcast')
        logger = logging.getLogger('pyTivo.beacon')
        for beacon_ip in beacon_ips.split():
            if beacon_ip != 'listen':
                try:
                    packet = beacon
                    bytes_sent = 0
                    while packet:
                        result = self.UDPSock.sendto(packet.encode('utf-8'), (beacon_ip, 2190))
                        if result < 0:
                            break
                        bytes_sent += result
                        packet = packet[result:]
                    logger.debug('Beacon broadcast: %d bytes to %s:2190' % (bytes_sent, beacon_ip))
                except Exception as e:
                    logger.error('Beacon broadcast failed to %s: %s' % (beacon_ip, str(e)))

    def start(self):
        self.send_beacon()
        self.timer = Timer(60, self.start)
        self.timer.start()

    def stop(self):
        self.timer.cancel()
        if self.bd:
            self.bd.shutdown()

    def recv_bytes(self, sock, length):
        block = b''
        while len(block) < length:
            add = sock.recv(length - len(block))
            if not add:
                break
            block += add
        return block

    def recv_packet(self, sock):
        length = struct.unpack('!I', self.recv_bytes(sock, 4))[0]
        return self.recv_bytes(sock, length)

    def send_packet(self, sock, packet):
        if isinstance(packet, str):
            packet = packet.encode('utf-8')
        sock.sendall(struct.pack('!I', len(packet)) + packet)

    def listen(self):
        """ For the direct-connect, TCP-style beacon """
        import _thread as thread

        def server():
            TCPSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            TCPSock.bind(('', 2190))
            TCPSock.listen(5)

            while True:
                # Wait for a connection
                client, address = TCPSock.accept()

                # Accept (and discard) the client's beacon
                self.recv_packet(client)

                # Send ours
                self.send_packet(client, self.format_beacon('connected'))

                client.close()

        thread.start_new_thread(server, ())

    def get_name(self, address):
        """ Exchange beacons, and extract the machine name. """
        our_beacon = self.format_beacon('connected', False)
        machine_name = re.compile('machine=(.*)\n').search

        try:
            tsock = socket.socket()
            tsock.connect((address, 2190))
            self.send_packet(tsock, our_beacon)
            tivo_beacon = self.recv_packet(tsock)
            tsock.close()
            if isinstance(tivo_beacon, bytes):
                tivo_beacon = tivo_beacon.decode('utf-8')
            name = machine_name(tivo_beacon).groups()[0]
        except:
            name = address

        return name
