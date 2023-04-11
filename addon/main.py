#!/usr/bin/env python3

import os
import sys
import yaml
import subprocess
import logging
from signal import signal
from json import dumps as json_dumps, loads as json_loads, load as json_load
from json.decoder import JSONDecodeError
import paho.mqtt.client as mqtt
from paho.mqtt import MQTTException

def shutdown(signum, frame):
    pass

def setup_log(log_level='DEBUG'):
    # Looging setup
    logger = logging.getLogger()
    if log_level.upper() == 'INFO':
        log_level = logging.INFO
    elif log_level.upper() == 'DEBUG':
        log_level = logging.DEBUG
    elif log_level.upper() == 'NONE':
        log_level = logging.CRITICAL
    logger.setLevel(log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

'''
Merge 2 dicts with recursion
'''
def merge_config(defaults, tomerge):
    merged = {}
    for k in defaults.keys():
        if k in tomerge.keys():
            merged[k] = { **defaults[k], **tomerge[k] }
        else:
            merged[k] = { **defaults[k] }
    if 'meters' in tomerge:
        merged['meters'] = tomerge['meters']
    else:
        merged['meters'] = {}
    return merged

'''
load_config(<config_file>)
Usage example:
  load_config('/etc/rtlamr2mqtt.yaml')
'''
def load_config(config_path):
    # As we don't know the log level yet, let's use some defaults
    logger = logging.getLogger()
    log_level = logging.CRITICAL
    logger.setLevel(log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    ## --x-- ##
    # Set some defaults
    default_config = {
        'general': {
            'log_level': 'debug',
            'sleep_for': 300,
            'device_id': 'single',
            'rtltcp_server': 'local',
        },
        'mqtt': {
            'host': '127.0.0.1',
            'port': 1883,
            'keepalive': 60,
            'tls_enabled': False,
        },
        'custom_parameters': {
            'rtltcp': "-s 2048000",
            'rtlamr': "-unique=true",
        }
    }
    file_type = config_path[config_path.rfind('.'):]
    if file_type not in ['.yaml', '.yml', '.json', '.js']:
        logger.critical(f'Config file format not supported: {file_type}')
        sys.exit(-1)
    try:
        with open(config_path, 'r') as config_file:
            if file_type in ['.yaml', '.yml']:
                loaded_config = yaml.safe_load(config_file)
            elif file_type in ['.json', '.js']:
                loaded_config = json_load(open(config_path))
        config_file.close()
    except Exception as e:
        logger.critical(f'Configuration file cannot be loaded at "{config_path}". Error: {e}')
        sys.exit(-1)
    # Update default_config with loaded_config
    return merge_config(default_config, loaded_config)


'''
Get configuration from HA Supervisor
'''
def get_config_from_supervisor(logger):
    import requests
    mqtt_config = {}
    api_url = "http://supervisor/services/mqtt"
    headers = {"Authorization": "Bearer " + os.getenv("SUPERVISOR_TOKEN")}
    logger.info(f'Fetching default MQTT configuration from {api_url}')
    try:
        resp = requests.get(api_url, headers=headers)
        if resp.status_code == requests.codes.ok
            d = resp.json()['data']
            mqtt_config['host'] = d.get('host')
            mqtt_config['port'] = int(d.get('port'))
            mqtt_config['user'] = d.get('username', None)
            mqtt_config['password'] = d.get('password', None)
            mqtt_config['tls_enabled'] = d.get('ssl', False)
    except Exception as e:
        logger.critical(f'Could not fetch default MQTT configuration from Supervisor: {e}')

    return mqtt_config

'''
usb_reset(<usb_port>)
Usage example:
  reset_usb_device('001:002')
'''
def reset_usb_device(usbdev, logger):
    from stat import S_ISCHR
    from fcntl import ioctl
    if usbdev is not None and ':' in usbdev:
        busnum, devnum = usbdev.split(':')
        filename = "/dev/bus/usb/{:03d}/{:03d}".format(int(busnum), int(devnum))
        if os.path.exists(filename) and S_ISCHR(os.stat(filename).st_mode):
            logging.info(f'Reseting USB device: {filename}')
            USBDEVFS_RESET = ord('U') << (4*2) | 20
            fd = open(filename, "wb")
            if int(ioctl(fd, USBDEVFS_RESET, 0)) != 0:
                logger.error(f'Error reseting USB device: "{usbdev}".')
            else:
                logger.info('Reset sucessful.')
            fd.close()


'''
MQTT Callbacks
'''
def mqtt_on_connect(client, userdata, flags, rc, buff):
    msg = str(rc)
    logger = userdata['logger']
    logger.info(f'Client connected with result: {msg}')

def mqtt_on_publish(client, userdata, mid):
    result = str(mid)
    logger = userdata['logger']
    logger.info(f'Message published: {result}')

def mqtt_on_disconnect(client, userdata, rc):
    logger = userdata['logger']
    if rc != 0:
        logger.warning("Unexpected disconnection.")

'''
mqtt_config = {host='127.0.0.1', port=1883, keepalive=60, use_tls=true}
mqtt_client(<mqtt_config>)
tls = { ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS, ciphers=None }
'''
def mqtt_client_setup(mqtt_config, logger):
    # Set some parameters needed by MQTT
    base_topic = mqtt_config['base_topic']
    mqtt_config['lwt_topic'] = f'{base_topic}/status'

    # Create client instance
    client = mqtt.Client(client_id="rtlamr2mqtt", protocol=mqtt.MQTTv5)

    if mqtt_config['tls_enabled']:
        # Set TLS configuration
        cert_reqs = ssl.CERT_NONE if mqtt_config['tls_insecure'] else ssl.CERT_REQUIRED
        client.tls_set(ca_certs=mqtt_config['tls_ca'], certfile=mqtt_config['tls_cert'], keyfile=mqtt_config['tls_keyfile'], cert_reqs=cert_reqs)
        client.tls_insecure_set(mqtt_config['tls_insecure'])

    # Enable logging
    if logger is not None:
        client.enable_logger(logger)
    else:
        client.enable_logger()

    # Set username and password if needed
    if ('user' in mqtt_config) and ('password' in mqtt_config):
        client.username_pw_set(mqtt_config['user'], password=mqtt_config['password'])

    # Set last will
    client.will_set(topic=mqtt_config['lwt_topic'], payload='Off', qos=1, retain=False)
    # Set reconnect parameters
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    # Set userdata
    client.user_data_set({'logger': logger})
    # Output connection parameters
    for k,v in mqtt_config.items():
        if k == 'password':
            logger.debug(f' MQTT Parameter: {k.upper()} => *** REDACTED *** ')
        else:
            logger.debug(f' MQTT Parameter: {k.upper()} => "{v}"')

    # Connect client
    client.connect_async(host=mqtt_config['host'], port=int(mqtt_config['port']), keepalive=int(mqtt_config['keepalive']))
    # Set callbacks
    client.on_connect = mqtt_on_connect
    client.on_publish = mqtt_on_publish
    client.on_disconnect = mqtt_on_disconnect
    # Start the mqtt client thread
    client.loop_start()
    # Publish Online status
    client.publish(topic=mqtt_config['lwt_topic'], payload='On', qos=1);

    return client

def start_rtl_subprocess():
    rtltcp = subprocess.Popen(rtltcp_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True, universal_newlines=True)
    rtlamr = subprocess.Popen(rtlamr_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True, universal_newlines=True)
    return (rtltcp, rtlamr)

def setup():
    # Setup shutdown callback
    signal(signal.SIGTERM, shutdown)
    signal(signal.SIGINT, shutdown)

    ## Running as Add-on?
    running_as_addon = False
    if os.getenv("SUPERVISOR_TOKEN") is not None:
        running_as_addon = True

    # Set config location
    config_path = '/data/options.json' if len(sys.argv) != 2 else sys.argv[1]
    # Load configuration
    main_config = load_config(config_path)
    # Set log level
    logger = setup_log(main_config['general']['log_level'])
    # Say hello!
    logger.info('Starting RTLAMR2MQTT.')
    if running_as_addon:
        logger.info('>>> Add-on detected.')
    # If we are running as add-on, load mqtt from supervisor
    if running_as_addon:
        mqtt_config_from_supervisor = get_config_from_supervisor(logger)
        # Merge main config with Supervisor MQTT config
        main_config['mqtt'].update(mqtt_config_from_supervisor)
    # Start MQTT client
    mqttc = mqtt_client_setup(main_config['mqtt'], logger)

    return (main_config, mqttc, logger)


def main():
    ## Running as Add-on?
    running_as_addon = False
    if os.getenv("SUPERVISOR_TOKEN") is not None:
        running_as_addon = True
    main_config, mqttc, logger = setup()
    while True:
        pass

if __name__ == "__main__":
    main()