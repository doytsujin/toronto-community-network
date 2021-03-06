#!/usr/bin/python3

import sys

if sys.version_info[0] < 3:
    raise Exception("Must be using Python 3")

import http.server
if sys.version_info[1] < 7:
    # Can't use threaded HTTP server, which is new in 3.7
    server_class = http.server.HTTPServer
else:
    server_class = http.server.ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler

import requests
from urllib.parse import urlparse, parse_qs
import urllib3
import os

# Settings
API_KEY = os.environ["UNMS_KEY"]
HEADERS = {"x-auth-token": API_KEY}
TIMEOUT = 5  # In seconds
SERVER_ADDRESS = ('', 8000)

if "UNMS_HOST" in os.environ:
    UNMS_HOST = os.environ["UNMS_HOST"]
else:
    UNMS_HOST = "unms.tomesh.net"


VERSION = "0.3.1"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_devices_json():
    r = requests.get("https://" + UNMS_HOST + "/nms/api/v2.1/devices", verify=False, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()  # Error if not a 200 OK response
    return r.json()


def get_ifaces_json(device_id):
    """
    Returns interface JSON, for the device id provided.
    """

    r = requests.get("https://" + UNMS_HOST + "/nms/api/v2.1/devices/" + device_id + "/interfaces", verify=False, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_airmax_json(device_id):
    """
    Returns airmax JSON, for the device id provided.
    """

    r = requests.get("https://" + UNMS_HOST + "/nms/api/v2.1/devices/airmaxes/" + device_id + "?withStations=true", verify=False, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def find_device_id_by_name(name, devices):
    for dev in devices:
        if dev["identification"]["name"] == name:
            return dev["identification"]["id"]
    return ""


def find_device_id_by_ip(ip, devices):
    for dev in devices:
        if dev["ipAddress"].split('/')[0] == ip:
            return dev["identification"]["id"]
    return ""


def write_prometheus_data(target_id, dev, ifaces, airmax, writer):
    """
    Writes a string of prometheus data, using the passed JSON.

    dev:     A single device in the devices JSON, in Python format.
    ifaces:  Interfaces JSON for the target (using the target's device ID), in Python format.
    airmax:  airmax JSON, using the target's device ID, in Python format.

    writer:
        Where data is written to. Any class with a write() method will work.
        sys.stdout can be used to print to stdout. This allows data to be streamed!
    """

    def write(string):
        writer.write(string.encode()+b"\n")

    write('unms_exporter_version{version="' + VERSION + '"} 1')

    if dev["identification"]["id"] != target_id:
        return

    write('node_uname_info{nodename="' + dev['identification']['name'] + '", sysname="' +  dev['identification']['model'] + '", release="' +  dev['identification']['firmwareVersion'] + '"} 1')
    write("node_cpu_ram " + str(dev['overview']['ram']))
    write("node_cpu_usage " + str(dev['overview']['cpu']))
    write("node_boot_time_seconds " + str(dev['overview']['uptime']))

    if dev['overview'].get('frequency') is not None:
        write("wireless_frequency " + str(dev['overview']['frequency']))

    if dev['overview'].get("signal") is not None:
        write("wireless_signal " + str(dev['overview']["signal"]))

    if dev['overview'].get("downlinkCapacity") is not None:
        write("ubnt_downlinkCapacity " + str(dev['overview']['downlinkCapacity']))
        write("ubnt_uplinkCapacity " + str(dev['overview']['uplinkCapacity']))

    if dev['overview'].get("linkScore") is not None:
        write("ubnt_theoreticalUplinkCapacity " + str(dev['overview']['theoreticalUplinkCapacity']))
        write("ubnt_theoreticalDownlinkCapacity " + str(dev['overview']['theoreticalDownlinkCapacity']))
        write("ubnt_theoreticalMaxUplinkCapacity " + str(dev['overview']['theoreticalMaxUplinkCapacity']))
        write("ubnt_theoreticalMaxDownlinkCapacity " + str(dev['overview']['theoreticalMaxDownlinkCapacity']))

        write("wireless_channelWidth " + str(dev['overview']['channelWidth']))
        write("wireless_transmitPower " + str(dev['overview']['transmitPower']))

        write("ubnt_stationsCount " + str(dev['overview']['stationsCount']))

    if airmax.get("airmax") is not None:
        mode = airmax['airmax']['wirelessMode']
        write("ubnt_noiseFloor " + str(airmax['airmax']['noiseFloor']))
        write("ubnt_wlanRxBytes " + str(airmax['airmax']['wlanRxBytes']))
        write("ubnt_wlanTxBytes " + str(airmax['airmax']['wlanTxBytes']))

        for iface in airmax['interfaces']:
            ifname = iface['identification']['name']
            ifmac = iface['identification']['mac']
            if iface.get("stations") is not None:
                for stn in iface["stations"]:
                    write('wireless_link_uptime{type="' + mode + '" device="' + ifname + '" sourcemac="' + ifmac + '" targetmac="' + stn["mac"] + '"} ' + str(stn["uptime"]))
                    write('wireless_link_latency{type="' + mode + '" device="' + ifname + '" sourcemac="' + ifmac + '" targetmac="' + stn["mac"] + '"} ' + str(stn["latency"]))
                    write('wireless_link_receive_bytes_total{type="' + mode + '" device="' + ifname + '" sourcemac="' + ifmac + '" targetmac="' + stn["mac"] + '"} ' + str(stn["rxBytes"]))
                    write('wireless_link_transmit_bytes_total{type="' + mode + '" device="' + ifname + '" sourcemac="' + ifmac + '" targetmac="' + stn["mac"] + '"} ' + str(stn["txBytes"]))
                    write('wirlesss_link_receive_signal{type="' + mode + '" device="' + ifname + '" sourcemac="' + ifmac + '" targetmac="' + stn["mac"] + '"} ' + str(stn["rxSignal"]))
                    write('wireless_link_transmit_signal{type="' + mode + '" device="' + ifname + '" sourcemac="' + ifmac + '" targetmac="' + stn["mac"] + '"} ' + str(stn["txSignal"]))

    for iface in ifaces:
        name = iface['identification']['name']

        if iface['status']['status'] == 'active':
            write('node_network_up{device="' + name + '"} 1')
        else:
            write('node_network_up{device="' + name + '"} 0')

        write('node_network_receive_bytes_total{device="' + name + '"} ' + str(iface['statistics']['rxbytes']))
        write('node_network_transmit_bytes_total{device="' + name + '"} ' + str(iface['statistics']['txbytes']))
        write('node_network_receive_rate{device="' + name + '"} ' + str(iface["statistics"]["rxrate"]))
        write('node_network_transmit_rate{device="' + name + '"} ' + str(iface["statistics"]["txrate"]))
        write('node_network_mtu_bytes{device="' + name + '"} ' + str(iface["mtu"]))
        write('node_network_dropped_total{device="' + name + '"} ' + str(iface["statistics"]["dropped"]))  # Not sure whether receive or transmit, or both


class HTTPRequestHandler(BaseHTTPRequestHandler):

    server_version = "unms_exporter/" + VERSION
    error_content_type = "text/plain"
    error_message_format = "%(code)d %(message)s\n%(explain)s"

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path != "/metrics":
            self.send_error(404)
            return

        # Verify target string
        params = parse_qs(parsed.query)
        if "target" in params:
            target = params["target"][-1]
            ttype = "ip"  # Target type
        elif "targetName" in params:
            target = params["targetName"][-1]
            ttype = "name"
        else:
            self.send_error(400, explain="No target provided.")
            return

        try:
            devices = get_devices_json()
            if ttype == "ip":
                target_id = find_device_id_by_ip(target, devices)
            elif ttype == "name":
                target_id = find_device_id_by_name(target, devices)

            if target_id == "":
                self.send_error(400, explain="Provided target name/IP does not exist.")
                return

            ifaces = get_ifaces_json(target_id)
            airmax = get_airmax_json(target_id)

        except Exception as e:
            self.send_error(500, explain=e.__str__())
            return

        # Check if node is down
        for dev in devices:
            if dev["identification"]["id"] != target_id:
                continue
            if dev['overview']['ram'] is None or dev['overview']['cpu'] is None:
                self.send_error(502, explain="Node is down")  # Bad gateway error
                return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        write_prometheus_data(target_id, dev, ifaces, airmax, self.wfile)


def main():
    httpd = server_class(SERVER_ADDRESS, HTTPRequestHandler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
