#!/usr/bin/env python3

# Python 3: Disable bytecode generation to avoid caching issues
import sys
sys.dont_write_bytecode = True

import logging
import os
import platform
import time

try:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass

import beacon
import config
import httpserver

def exceptionLogger(*args):
    sys.excepthook = sys.__excepthook__
    logging.getLogger('pyTivo').error('Exception in pyTivo', exc_info=args)

def last_date():
    lasttime = -1
    path = os.path.dirname(__file__)
    if not path:
        path = '.'
    for root, dirs, files in os.walk(path):
        for name in files:
            if name.endswith('.py'):
                tm = os.path.getmtime(os.path.join(root, name))
                if tm > lasttime:
                    lasttime = tm

    return time.asctime(time.localtime(lasttime))

def setup(in_service=False):
    config.init(sys.argv[1:])
    config.init_logging()
    sys.excepthook = exceptionLogger

    port = config.getPort()

    httpd = httpserver.TivoHTTPServer(('', int(port)),
        httpserver.TivoHTTPHandler)

    logger = logging.getLogger('pyTivo')
    logger.info('Last modified: ' + last_date())
    logger.info('Python: ' + platform.python_version())
    logger.info('System: ' + platform.platform())

    for section, settings in config.getShares():
        # Validate path for shares that have one
        if 'path' in settings:
            share_path = settings['path']
            if os.path.isdir(share_path):
                logger.info('Share [%s]: path found: %s' % (section, share_path))
            else:
                logger.error('Share [%s]: path not found: %s' % (section, share_path))
        httpd.add_container(section, settings)

    b = beacon.Beacon()
    b.add_service('TiVoMediaServer:%s/http' % port)
    b.start()
    if 'listen' in config.getBeaconAddresses():
        b.listen()

    httpd.set_beacon(b)
    httpd.set_service_status(in_service)

    logger.info('pyTivo is ready.')
    return httpd

def serve(httpd):
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

def mainloop():
    httpd = setup()
    serve(httpd)
    httpd.beacon.stop()
    return httpd.restart 

if __name__ == '__main__':
    while mainloop():
        time.sleep(5)
