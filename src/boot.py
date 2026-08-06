# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)

import network
import time

def checkwlan():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.active(True)
        wlan.connect('WIFI_SSID', 'WIFI_PASSWORD')
        for _ in range(150):  # ~15s - don't hang forever if the AP is unreachable
            if wlan.isconnected():
                break
            time.sleep_ms(100)
    print('network config:', wlan.ifconfig() if wlan.isconnected() else 'NOT CONNECTED')

checkwlan()

try:
    import webrepl
    webrepl.start()
except Exception as e:
    # Never let an unconfigured/broken webrepl stop main.py from starting.
    print('webrepl not started:', e)
