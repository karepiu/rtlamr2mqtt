#!/usr/bin/env python3

import os
import sys
import re
import json
import signal
import subprocess
import socket
import ssl
import warnings
from datetime import datetime
from json import dumps, loads
from json.decoder import JSONDecodeError
from random import randrange
from struct import pack
from time import sleep, time
from fcntl import ioctl
from stat import S_ISCHR
import yaml
import requests
import usb.core
import paho.mqtt.publish as publish
from paho.mqtt import MQTTException

def log_message(message):
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d %H:%M:%S")
    print('[{}] {}'.format(dt_string, message), file=sys.stderr)


class Configuration:
    def __init__(self, config_file = '/etc/rtlamr2mqtt.yaml'):
        self.config_file = config_file
        self.config_defaults = {
            'general': {
                'sleep_for': 300,
                'verbosity': 'info',
                'tickle_rtl_tcp': False,
                'device_id': 'single',
                'rtltcp_server': '127.0.0.1:1234',
            },
            'mqtt': {
                'host': '127.0.0.1',
                'user': None,
                'password': None,
                'tls_enabled': False,
                'tls_ca': '/etc/ssl/certs/ca-certificates.crt',
                'tls_insecure': True,
                'ha_autodiscovery': True,
                'ha_autodiscovery_topic': 'homeassistant',
                'base_topic': 'rtlamr'
            },
            'custom_parameters': {
                'rtltcp': "-s 2048000",
                'rtlamr': "-unique=true",
            },
        }

def main():
    if len(argv) != 2:
         config_file = ["/data/options.json", "/etc/rtlamr2mqtt.yaml"]
    else:
        config_file = [argv[1]]
    for cf in config_file:
        if os.path.exists(cf):
            config_path = cf
            log_message('Using "{}" config file'.format(config_path))
            break
    config = Configuration('/etc/rtlamr2mqtt.yaml')
    pass

if __name__ == '__main__':
    main()
