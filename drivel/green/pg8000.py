def _patch():
    from eventlet import patcher
    from eventlet.green import select
    from eventlet.green import socket
    from eventlet.green import threading
    from eventlet.green import time
    protocol = patcher.import_patched('pg8000.interface',
        socket=socket,
        threading=threading)

    interface = patcher.import_patched('pg8000.protocol',
        protocol=protocol,
        socket=socket,
        select=select,
        threading=threading)

    return patcher.import_patched('pg8000.dbapi',
        time=time,
        interface=interface,
        threading=threading)

pg8000_dbapi = DBAPI = _patch()

