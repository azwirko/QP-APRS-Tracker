#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 11 19:43:40 2022
Updated 07-25-23

@author: Andy Zwirko K1RA
         k1ra@k1ra.us

        State QSO Party Mobile Tracker
        Utilizing APRS lat/lon data from APRS-IS
        Leaflet and OpenStreetMaps for mapping
        County KML from NO5W for county boundaries
        arGeoDetector by Rich K3FRG for determining county names

./APRSGeoDetector.py --cli -a noam.aprs2.net -t 14580 -b boundaries/OverlayVirginiaRev4.kml -o 1800 -s vaqp-calls.txt
"""
import json
import os
import os.path
from os import path
import signal
import sys
import math
import re
import time
import datetime
import threading
from threading import Thread
import logging
import logging.handlers
import xml.etree.ElementTree
import telnetlib

from enum import Enum

from appdirs import AppDirs
from optparse import OptionParser
from configparser import ConfigParser


VERSION = "1.0.1"

# APRS-IS filter command for narrowing APRS packets from within state boundaries (approximate)
geofilter = b"#filter a/39.372680/-83.26599638/36.567059/-74.973329"

# regex search string for APRS packets participating in QSO Party
qpstring = "VQP|VAQP"

# directory for www HTML files
wwwdir = "www/"

class geoMsg(Enum):
    GRID = 1
    CNTY = 2
    STAT = 3
    TIME = 4
    APRS = 5
    NOTIF = 6
    POPUP = 7
    REPLAY = 8


class geoBoundary():
    def __init__(self, name, abbr):
        self.name = name
        self.abbr = abbr
        self.coords = []

    def addCoord(self, xy):
        # xy is a (x,y) tuple
        self.coords.append(xy)

    def wrapCoord(self):
        self.coords.append(self.coords[0])

    def coords2mxb(self, c1, c2):
        # solve for line equation
        (c1x, c1y) = c1
        (c2x, c2y) = c2

        m = (c2y - c1y) / (c2x - c1x)
        b = c1y - m * c1x
        # print "m>%f b>%f" % (m, b)
        return (m, b)

    def contains(self, xy):
        (x, y) = xy

        test_cnt = 0
        coord_cnt = 0

        for i in range(len(self.coords) - 1):
            # Test against sequential coordinates
            (cx1, cy1) = self.coords[i]
            (cx2, cy2) = self.coords[i + 1]
            # the GPS X coordinate must fall between the two test coords
            if x == cx1:
                if cy1 < y:
                    test_cnt -= 1
                else:
                    test_cnt += 1
                coord_cnt += 1

            elif x == cx2:
                if cy2 < y:
                    test_cnt -= 1
                else:
                    test_cnt += 1
                coord_cnt += 1

            elif x >= cx1 and x <= cx2 or x >= cx2 and x <= cx1:
                # Solve for line equation y=mx+b
                (m, b) = self.coords2mxb(self.coords[i], self.coords[i + 1])
                # Calculate Y coordinate from equation
                ycalc = m * x + b

                # Compare calculated Y vs GPS Y
                if ycalc < y:
                    test_cnt -= 1
                else:
                    test_cnt += 1

                # Record how many coordinate pairs satisfy the test
                coord_cnt += 1

        #     print("%s: %d %d" % (self.abbr, test_cnt, coord_cnt))
        if not ((coord_cnt - abs(test_cnt)) % 4 == 0):
            # print("TRUE> %s: %d %d" % (self.abbr, test_cnt, coord_cnt))
            return True
        else:
            return False


class APRSGeoDetector(Thread):
    def __init__(self, aprs_host, aprs_tcp, cb, age_out, log=0, aprslog=0, mode=0):
        Thread.__init__(self)

        self.callsFile = None
        self.callsTime = None
        self.age_out = age_out
        self.calls = []
        self.db = {}
        self.aprs_is_open = False
        self.boundaries = []
        self.mode = 0  # 0 = gui, 1 = cli
        self.verbose = False

        self.log_main = log
        self.log_aprs = aprslog

        self.last_datetime = datetime.datetime.now(datetime.timezone.utc)

        self.aprs = telnetlib.Telnet()
        self.aprs_host = aprs_host
        self.aprs_port = aprs_tcp

        self.aprs_lock = False
        self.aprs_datetime = datetime.datetime.now(datetime.timezone.utc)

        self.bnd_warn = 0

        self.state = 0
        self.in_state = -1
        self._do_exit = 0
        self.lock = threading.Lock()

        self.msgCB = cb

    def loadBoundaries(self, filename):
        self.boundaries = []

        # Load Kml file into string so I can remove the 
        # xmlns="http://earth.google.com/kml/2.1" string
        # from the <kml> tag.  I don't know why but this 
        # breaks the subsequent element tree?????

        xmlstr = ""
        try:
            kmlin = open(filename)
            for line in kmlin.readlines():
                xmlstr += line.replace(" xmlns=\"http://earth.google.com/kml/2.1\"", "")
        except:
            self.msgCB((geoMsg.STAT, "Error reading boundary file [%s]!" % filename))
            print("Error reading boundary file [%s]!" % filename)
            # quit(1)
            return

        e = xml.etree.ElementTree.fromstring(xmlstr)
        # e = xml.etree.ElementTree.parse(filename).getroot()

        for xplacemark in e[0].iter('Placemark'):
            for xname in xplacemark.iter('name'):
                # extract name info
                # Form: 'Fauquier=FAU 1'
                # only process '1' entries
                m = re.search('(\w+)=(\w+)', xname.text)
                if (m):  # If match succeeds
                    name = m.group(1)
                    abbr = m.group(2)
                    self.log("Loading %s(%s)" % (abbr, name))
                    # Create new boundary object
                    bnd = geoBoundary(name, abbr)

                    # Add coordinates to boundary object
                    # Form: '-75.87614423,37.55153989'
                    for xcoords in xplacemark.iter('coordinates'):
                        lines = xcoords.text.strip().split('\n')
                        for line in lines:
                            sline = line.strip()  # remove whitespace
                            xy = sline.split(',')
                            # print ("X> %s, Y> %s" % (xy[0], xy[1]))
                            # Add coordinate to object
                            bnd.addCoord((float(xy[0]), float(xy[1])))

                        # Wrap coordinate list by copying entry 0 to the end
                        bnd.wrapCoord()

                    self.boundaries.append(bnd)
        self.log("Boundary file loaded")


    def loadCalls(self, filename):
        self.calls = []
        self.callsTime = os.stat(filename).st_mtime
        self.callsFile = filename

        try:
            calls = open(filename)
            for line in calls.readlines():
                line = re.sub("\n", "", line)
                self.calls.append(line)
        except:
            self.msgCB((geoMsg.STAT, "Error reading QP calls file [%s]!" % filename))
            # print ("Error reading QP calls file [%s]!" % filename)
            # quit(1)
            return

    def log(self, logstr, status=1):
        if self.log_main:
            self.log_main.info(logstr)

        if status:
            self.msgCB((geoMsg.STAT, logstr))

    def logAPRS(self, logstr):
        if self.log_aprs:
            self.log_aprs.info(logstr)

    def wdTick(self):
        self.wd = datetime.datetime.now()

    def wdCheck(self, timeout=15):
        if datetime.datetime.now() - self.wd > datetime.timedelta(minutes=timeout):
            # self._do_exit = 1
            return 1
        return 0

    def openAPRS(self):
        # print ("open APRS")
        try:
            self.aprs.open(self.aprs_host, port=self.aprs_port)
        except:
            self.log("Error opening APRS host [%s]" % self.aprs_host)
            time.sleep(5)
        else:
            self.log("opening APRS connection")
            with self.lock:
                if not self.aprs_is_open:
                    self.log("openAPRS")
                    self.aprs_is_open = True
            return True

    def sendAPRS(self, msg: str):
        try:
            self.aprs.write(bytes(msg))
            self.aprs.write(b"\n")
        except:
            self.log("Error sending to APRS host [%s]" % self.aprs_host)
            with self.lock:
                self.log("sendAPRS")
                self.aprs.close()
            return False
        else:
            self.logAPRS("APRS message sent: " + str(msg))
            return True

    def recvAPRS(self, msg: str):
        try:
            buf = str(self.aprs.read_until(bytes(msg), timeout=120))
        except:
            self.log("Error receiving from APRS host [%s]" % self.aprs_host)
            self.log(self.state)

            if self.wdCheck(1):
                self.log("Timeout waiting for APRS data")
                self.closeAPRS()

            print("sleep 5")
            time.sleep(5)
            return ""
        else:
            return buf

    def send_recvAPRS(self, smsg: str, rmsg: str):
        if self.sendAPRS(smsg):
            if self.recvAPRS(rmsg):
                return True
            else:
                return False
        else:
            return False

    def closeAPRS(self):
        self.log("close APRS")
        with self.lock:
            self.state = 1

            # if self.aprs_is_open:
            self.aprs.close()
            self.aprs_is_open = False

    def stop(self):
        self._do_exit = 1

    def run(self):
        ## Telnet Thread

        ## States
        ## 0 = Wait for APRS host information
        ## 1 = Open APRS host
        ## 2 = Wait for APRS host data
        ## 3 = Wait for APRS Time/Date sync
        ## 4 = Process APRS data

        self.wdTick()
        # self.state = 1

        while not self._do_exit:
            # State 0
            if self.state == 0:
                self.in_state = 0
                self.log("Idle")
                # auto exit if in cli mode
                if self.mode == 1:
                    self._do_exit = 1
                while self.state == 0 and not self._do_exit:
                    time.sleep(1)

            # State 1
            if self.state == 1:
                self.in_state = 1

                self.log("Reading any available, prior JSON backup files")
                self.readJSON(self.db)
                # print(self.db)

                self.log("Opening APRS host [%s : %s]" % (self.aprs_host, self.aprs_port))
                fails_to_go = 5
                while self.state == 1 and not self._do_exit:
                    if self.openAPRS():
                        self.state = 2
                    else:
                        fails_to_go -= 1
                        if not fails_to_go:
                            self.state = 1
                            break

                    time.sleep(2)

            # State 2
            if self.state == 2:
                self.in_state = 2
                self.log("Waiting for initial APRS connect")

                fails_to_go = 5
                while self.state == 2 and not self._do_exit:
                    if self.recvAPRS(b"# "):
                        self.state = 3
                    else:
                        fails_to_go -= 1
                        if not fails_to_go:
                            self.closeAPRS()
                            self.log("Timeout waiting for APRS host [%s] login" % self.aprs_host)

                        time.sleep(2)

            # State 3
            if self.state == 3:
                self.in_state = 3
                self.log("Waiting for successful login")

                fails_to_go = 5
                while self.state == 3 and not self._do_exit:
                    if self.send_recvAPRS(b"user NOCALL pass -1 vers test 1.0", b"# logresp"):
                        self.log("Waiting for successful filter setup")

                        if self.send_recvAPRS(geofilter, b"active"):
                            self.state = 4
                        else:
                            fails_to_go -= 1
                            if not fails_to_go:
                                self.closeAPRS()
                                self.log("Error sending/receiving message APRS host [%s]" % self.aprs_host)

                            time.sleep(2)
                    else:
                        fails_to_go -= 1
                        if not fails_to_go:
                            self.closeAPRS()
                            self.log("Error sending/receiving message APRS host [%s]" % self.aprs_host)

                        time.sleep(2)

            # State 4
            if self.state == 4:
                self.in_state = 4
                self.log("Processing APRS data")

                fails_to_go = 5
                while self.state == 4 and not self._do_exit:
                    caicChanged = False
                    grid4Changed = False
                    grid6Changed = False

                    # with self.lock:
                    buf = str(self.recvAPRS(b"\n"))
                    # self.log(buf)

                    # check if error retrieving APRS data
                    if buf == "":
                        self.log("empty buffer")
                        fails_to_go -= 1
                        self.log(fails_to_go)
                        if not fails_to_go:
                            self.log("State 4, error receiving message APRS host [%s]" % self.aprs_host)
                            self.closeAPRS()

                        continue

                    # reset watchdog time as APRS-IS is alive
                    self.wdTick()

                    # skip any status lines
                    if re.search('^#', buf):
                        # print("status line")
                        continue
                    else:
                        # look for APRS lines starting with CALL1-n>
                        m = re.search("([A-Z]{1,2}\d[A-Z]{1,3}[\-\d]*)\>", buf)
                        # if match
                        if m:
                            # extract CALL1-n
                            call = m[1]
                            self.logAPRS(buf)
                            # self.log(buf)
                        else:
                            # not a standard APRS call
                            continue

                        # Try to extract a decimal lat/lon from packet
                        try:
                            xy = self.getAPRSCoords(buf)
                        except ValueError:
                            # no GPS lat/lon found
                            # print("Get Coords Error: ", buf)
                            continue

                        # if call not seen, initialize dict
                        if call not in self.db:
                            self.db[call] = {}

                        if re.search(qpstring, buf, re.IGNORECASE):
                            if call not in self.calls:
                                self.calls.append(call)

                                with open(self.callsFile, 'a') as f:
                                    print(call, file=f)
                                f.close()

                        # search for any registered QP calls or any calls beaconing QP search string
                        if call in self.calls:
                            # tag as a QSO PARTY APRS call
                            self.db[call]['qsop'] = True
                        else:
                            # tag as a regular APRS call
                            self.db[call]['qsop'] = False

                        # save lat/lon and time recorded
                        self.db[call]['lonlat'] = xy
                        self.db[call]['lonlat_time'] = int(time.time())

                        # determine 6-digit grid square
                        grid6 = self.calcGridSquare(xy)
                        # print(" " + grid6, end='')

                        # strip 6-digit to make 4-digit grid square
                        grid4 = grid6[0:3]

                        # have we saved a 6-digit grid for this call yet?
                        if "grid6" in self.db[call]:
                            # yes
                            self.msgCB((geoMsg.GRID, grid6))

                            # test if this is a new 6-digit grid
                            if self.db[call]['grid6'] != grid6:
                                # new grid detected save and time stamp
                                self.db[call]['grid6'] = grid6
                                self.db[call]['grid6_time'] = int(time.time())
                                # print(call, "WAS", self.db[call]['grid6'], "NOW", grid6, sep=" ")

                                grid6Changed = True
                        else:
                            # first time for saving a 6-digit grid and timestamp for call
                            self.db[call]['grid6'] = grid6
                            self.db[call]['grid6_time'] = int(time.time())
                            # print("NEW", call, grid6, sep=" ")

                            grid6Changed = True

                        # determine if coordinates are within state boundaries and find county/city
                        caic = self.findCAIC(xy)

                        # have we defined a county/city above
                        if not hasattr(caic, "abbr"):
                            # NO!
                            continue

                        # does GPS map to an unknown state county or city
                        if caic.abbr == "UNK":
                            # yes delete call entry from database
                            del self.db[call]
                            continue
                        else:
                            self.msgCB((geoMsg.CNTY, (caic.name, caic.abbr)))

                            # valid county/city - have we saved it for this call yet
                            if "caic_abbr" in self.db[call]:
                                # yes - check if county/city has changed
                                if self.db[call]['caic_abbr'] != caic.abbr:
                                    # New county/city detected
                                    self.db[call]['caic_abbr'] = caic.abbr
                                    self.db[call]['caic_name'] = caic.name
                                    self.db[call]['caic_time'] = int(time.time())
                                    # print(call, "WAS", self.db[call]['caic_abbr'], "NOW", caic.name,
                                    #       caic.abbr, sep=" ")

                                    caicChanged = True
                            else:
                                # first time saving county/city and timestamp for this call
                                self.db[call]['caic_abbr'] = caic.abbr
                                self.db[call]['caic_name'] = caic.name
                                self.db[call]['caic_time'] = int(time.time())
                                # print("NEW", call, caic.abbr, caic.name, sep=" ")

                                caicChanged = True

                            # has city/county changed for this call
                            # if caicChanged:
                            #     # update appropriate JSON map data file with latest info
                            #     self.writeJSON(self.db)
                            #     # self.log("Updated JSON")

                            # is it a registered or QP call
                            if self.db[call]['qsop']:
                                # yes
                                self.log("QP " + call)
                                self.writeJSON(self.db)
                            else:
                                # no - just regular APRS call
                                self.log("Non-QP " + call)

                        # always update registered county/city CSV file with timeout aging
                        self.writeCSV(self.db)
                        # self.log("Updated CSV")

                    if self.wdCheck(1):
                        self.log("Timeout waiting for APRS data, re-writing data")
                        with self.lock:
                            # self.aprs.close()
                            # self.state = 0
                            print("wdCheck(1)")
                            self.writeJSON(self.db)
                            self.writeCSV(self.db)

                    if self.wdCheck(3):
                        self.log("Long timeout waiting for APRS data, closing port")
                        with self.lock:
                            self.closeAPRS()
                            print("Closing APRS port")

                    # print(self.callsTime, os.stat(self.callsFile).st_mtime, sep= " ")

                    if self.callsTime != os.stat(self.callsFile).st_mtime:
                        self.log("Reloading QP calls list.")
                        self.loadCalls(self.callsFile)
                        self.callsTime = os.stat(self.callsFile).st_mtime

        # Clean up com if still open
        # if self.aprs_is_open:
        self.closeAPRS()

    def replayFile(self, filename, speed=0):
        self.log("Replaying {} APRS file".format(filename))
        with open(filename) as fp:
            for buf in fp:
                # print(buf)
                time.sleep(speed)
                # process APRS lines for date/time
                # MUST CHANGE SEARCH LINE
                m = str(buf)

                # look for APRS lines starting with CALL1-n>
                m = re.search("([A-Z]{1,2}\d[A-Z]{1,3}[\-\d]*)\>", buf)
                # if match
                if m:
                    # extract CALL1-n
                    call = m[1]
                    # self.logAPRS(buf)
                    # self.log(buf)
                else:
                    # not a standard APRS call
                    continue

                # Try to extract a decimal lat/lon from packet
                try:
                    xy = self.getAPRSCoords(buf)
                except ValueError:
                    # no GPS lat/lon found
                    # print("Get Coords Error: ", buf)
                    continue

                if re.search(qpstring, buf, re.IGNORECASE):
                    if call not in self.calls:
                        self.calls.append(call)

                        with open(self.callsFile, 'a') as f:
                            print(call, file=f)
                        f.close()

                # if call not seen, initialize dict
                if call not in self.db:
                    self.db[call] = {}

                # search for any registered QP calls or any calls signing QP search string
                if call in self.calls:
                    # tag as a QSO PARTY APRS call
                    self.db[call]['qsop'] = True
                else:
                    # tag as a regular APRS call
                    self.db[call]['qsop'] = False

                # save lat/lon and time recorded
                self.db[call]['lonlat'] = xy
                self.db[call]['lonlat_time'] = int(time.time())

                # determine 6-digit grid square
                grid6 = self.calcGridSquare(xy)
                # print(" " + grid6, end='')

                # strip 6-digit to make 4-digit grid square
                grid4 = grid6[0:3]

                # have we saved a 6-digit grid for this call yet?
                if "grid6" in self.db[call]:
                    # yes
                    self.msgCB((geoMsg.GRID, grid6))

                    # test if this is a new 6-digit grid
                    if self.db[call]['grid6'] != grid6:
                        # new grid detected save and time stamp
                        self.db[call]['grid6'] = grid6
                        self.db[call]['grid6_time'] = int(time.time())
                        # print(call, "WAS", self.db[call]['grid6'], "NOW", grid6, sep=" ")

                        grid6Changed = True
                else:
                    # first time for saving a 6-digit grid and timestamp for call
                    self.db[call]['grid6'] = grid6
                    self.db[call]['grid6_time'] = int(time.time())
                    # print("NEW", call, grid6, sep=" ")

                    grid6Changed = True

                # determine if coordinates are within state boundaries and find county/city
                caic = self.findCAIC(xy)

                # have we defined a county/city above
                if not hasattr(caic, "abbr"):
                    # NO!
                    continue

                # does GPS map to an unknown state county or city
                if caic.abbr == "UNK":
                    # yes delete call entry from database
                    del self.db[call]
                    continue
                else:
                    self.msgCB((geoMsg.CNTY, (caic.name, caic.abbr)))

                    # valid county/city - have we saved it for this call yet
                    if "caic_abbr" in self.db[call]:
                        # yes - check if county/city has changed
                        if self.db[call]['caic_abbr'] != caic.abbr:
                            # New county/city detected
                            self.db[call]['caic_abbr'] = caic.abbr
                            self.db[call]['caic_name'] = caic.name
                            self.db[call]['caic_time'] = int(time.time())
                            # print(call, "WAS", self.db[call]['caic_abbr'], "NOW", caic.name,
                            #       caic.abbr, sep=" ")

                            caicChanged = True
                    else:
                        # first time saving county/city and timestamp for this call
                        self.db[call]['caic_abbr'] = caic.abbr
                        self.db[call]['caic_name'] = caic.name
                        self.db[call]['caic_time'] = int(time.time())
                        # print("NEW", call, caic.abbr, caic.name, sep=" ")

                        caicChanged = True

                    # has city/county changed for this call
                    if caicChanged:
                        # update appropriate JSON map data file with latest info
                        self.writeJSON(self.db)
                        # self.log("Updated JSON")

                    # is it a registered or QP call
                    if self.db[call]['qsop']:
                        # yes
                        self.log("QP " + call)
                    else:
                        # no - just regular APRS call
                        self.log("Non-QP " + call)

                # always update registered county/city CSV file with timeout aging
                self.writeCSV(self.db)
                # self.log("Updated CSV")

        self.log("Replay complete")
        self.msgCB((geoMsg.REPLAY, 0))

    # Get location from APRS strings (3-4 types?)
    def getAPRSCoords(self, aprs_str):
        # W4VA-10>APDW14,WIDE1-1,WIDE2-1,qAR,W4TTU:!3844.04NR07750.16W&PHG3660Viewtree Mtn, Warrenton, VA FM18br
        # WD4ITN>APRS,TCPIP*,qAC,THIRD:@261903z3824.42N/07934.85W_333/002g...t044r...p...P000h50b10222.DsVP
        # W3VPS-7>S8UV6P,NV4FM-5,WIDE1*,WIDE2-1,qAR,W4KEL-12:`i+? ]F[/>"5"}^
        # KG4IXS>APDW16,TCPIP*,qAC,T2ALBERTA:!3653.32NR07927.01W#PHG7140Chatham, VA Remote Base\r\n'

        m = re.search(":(?!;).*(\d{4}\.[\d\s]{2})([NS]).{1,2}(\d{5}\.[\d\s]{2})([WE])", aprs_str)
        # print(aprs_str)
        if m:
            # print(m)
            aprs_y = m[1]
            aprs_yd = m[2]
            aprs_x = m[3]
            aprs_xd = m[4]

            y = float(aprs_y[0:2]) + (float(aprs_y[2:]) / 60.0)
            if aprs_yd == 'S':
                y = 0 - y

            x = float(aprs_x[0:3]) + (float(aprs_x[3:]) / 60.0)
            if aprs_xd == 'W':
                x = 0 - x

            self.msgCB((geoMsg.APRS, "%s%s  %s%s" % (aprs_y, aprs_yd, aprs_x, aprs_xd)))
            # print ("APRS(LON:%f,LAT:%f) \n" % (x, y))

            return x, y

        # MIC-E
        # W3VPS-7>S8UV6P,NV4FM-5,WIDE1*,WIDE2-1,qAR,W4KEL-12:`i+? ]F[/>"5"}^

        m = re.search(">(.{6}),.*:[`'](.{3})", aprs_str)
        if m:
            # print("MIC-e ", aprs_str)

            miclat = m[1]
            miclon = m[2]

            # print(miclat, miclon, sep=" ")

            # (Lat) Ar1DDDD0 Br1DDDD0 Cr1MMMM0 Nr1MMMM0 Lr1HHHH0 Wr1HHHH0 CrrSSID0
            # (Lon) F D+28 M+28 H+28 SP+28 DC+28 SE+28 $ T
            lat = (ord(miclat[0:1]) & 0b0001111) * 10 + (ord(miclat[1:2]) & 0b0001111) + \
                  ((ord(miclat[2:3]) & 0b0001111) * 10 + (ord(miclat[3:4]) & 0b0001111) +
                   ((ord(miclat[4:5]) & 0b0001111) * 10 + (ord(miclat[5:6]) & 0b0001111)) / 100.) / 60.

            lon = (ord(miclon[0:1])) - 28

            if (lon > 180) and (lon < 189):
                lon = lon - 80

            if (lon > 190) and (lon < 199):
                lon = lon - 190

            lon = lon + (((ord(miclat[5:6])) & 0b10000000) >> 7) * 100.

            lonm = ord(miclon[1:2]) - 28

            if lonm > 60:
                lonm = lonm - 60

            lon = -(lon + (lonm + (ord(miclon[2:3]) - 28) / 100.) / 60.)

            # print(lat, " ", lon)

            return lon, lat

        # if we get here, no GPS lat/lon found
        raise ValueError("APRS record does not contain valid coordinates")

    def findCAIC(self, xy):
        (nx, ny) = xy

        # return if bogus data
        if nx == 0 and ny == 0:
            return

        qth_list = []
        for bnd in self.boundaries:
            if bnd.contains(xy):
                qth_list.append(bnd)

        # If more than one boundaries match, solve for correct boundary
        # 1) city and county, find city in county
        # 2) county/county overlap, just pick one
        qth = False
        if len(qth_list) == 1:
            qth = qth_list[0]
        elif len(qth_list) > 1:
            for i in range(0, len(qth_list)):
                for j in range(0, len(qth_list)):
                    if i != j:
                        # print ("%s vs %s" % (qth_list[i].abbr, qth_list[j].abbr))
                        c = qth_list[j].coords[0]
                        if not qth_list[i].contains(c):
                            qth = qth_list[i]
        else:
            if self.bnd_warn == 0:
                # print("Warning: coordinate did not match boundary file")
                self.bnd_warn = 1
            return geoBoundary("Unknown", "UNK")

        if not qth:
            qth = qth_list[0]

        self.bnd_warn = 0

        # print("QTH> %s" % qth.abbr)

        return qth

    def calcGridSquare(self, xy):
        (nx, ny) = xy

        # move origin to bottom left of the world 
        nx += 180
        ny += 90

        # field is 20x10 degree rect
        xf = math.floor(nx / 20)
        yf = math.floor(ny / 10)

        # convert to ascii capitals A-R
        xfc = str(chr(65 + xf))
        yfc = str(chr(65 + yf))

        # square is 2x1 degree rect
        xs = math.floor((nx - (xf * 20)) / 2)
        ys = math.floor((ny - (yf * 10)) / 1)

        # convert to ascii numbers 0-9
        xsc = str(xs)
        ysc = str(ys)

        # subsquare is (2/24)x(1/24) degree rect
        xss = math.floor((nx - (xf * 20) - (xs * 2)) / (2 / 24))
        yss = math.floor((ny - (yf * 10) - (ys * 1)) / (1 / 24))

        # convert to ascii capitals A-R
        xssc = str(chr(97 + xss))
        yssc = str(chr(97 + yss))

        return ("%s%s%s%s%s%s" % (xfc, yfc, xsc, ysc, xssc, yssc))

    def readJSON(self, db):

        if path.exists(wwwdir + 'qso-party.json'):
            with open(wwwdir + 'qso-party.json') as json_file:
                try:
                    data = json.load(json_file)
                except:
                    pass
                else:
                    for feature in data['features']:
                        # print(feature['properties']['call'])
                        call = feature['properties']['call']
                        db[call] = {}
                        db[call]['scall'] = feature['properties']['scall']
                        db[call]['qsop'] = bool( feature['properties']['qsop'] == "True")
                        db[call]['caic_time'] = feature['properties']['caic_time']
                        db[call]['caic_abbr'] = feature['properties']['caic_abbr']
                        db[call]['caic_name'] = feature['properties']['caic_name']
                        db[call]['grid6_time'] = feature['properties']['grid6_time']
                        db[call]['grid6'] = feature['properties']['grid6']
                        db[call]['lonlat_time'] = feature['properties']['lonlat_time']
                        db[call]['lonlat'] = feature['geometry']['coordinates']

            json_file.close()

        if path.exists(wwwdir + 'non-qso-party.json'):
            with open(wwwdir + 'non-qso-party.json') as json_file:
                try:
                    data = json.load(json_file)
                except:
                    pass
                else:
                    for feature in data['features']:
                        # print(feature['properties']['call'])
                        call = feature['properties']['call']
                        db[call] = {}
                        db[call]['scall'] = feature['properties']['scall']
                        db[call]['qsop'] = bool( feature['properties']['qsop'] == "True")
                        db[call]['caic_time'] = feature['properties']['caic_time']
                        db[call]['caic_abbr'] = feature['properties']['caic_abbr']
                        db[call]['caic_name'] = feature['properties']['caic_name']
                        db[call]['grid6_time'] = feature['properties']['grid6_time']
                        db[call]['grid6'] = feature['properties']['grid6']
                        db[call]['lonlat_time'] = feature['properties']['lonlat_time']
                        db[call]['lonlat'] = feature['geometry']['coordinates']

            json_file.close()

        return

    def writeJSON(self, db):
        i = {}

        with open(wwwdir + 'qso-party.json', 'w') as f:
            # header
            print('{"type":"FeatureCollection","features":[', file=f)
        f.close()

        with open(wwwdir + 'non-qso-party.json', 'w') as f:
            # header
            print('{"type":"FeatureCollection","features":[', file=f)
        f.close()

        # id counter required for numbering markers for google maps
        id = 1

        # icon counter used by google maps
        icon = 1

        i['qso-party.json'] = 0
        i['non-qso-party.json'] = 0

        try:
            dbcalls = sorted(db.items(), key=lambda x: x[1]['caic_time'], reverse=True)
        except:
            # print(calls)
            self.log("writeJSON error")
            return

        # loop for every call saved in hash
        for dbcall in dbcalls:
            call = dbcall[0]
            # print(call)

            # extract lat/lon and time from db for call
            lonlat_time = dbcall[1]['lonlat_time']
            (lon, lat) = db[call]['lonlat']

            grid6 = dbcall[1]['grid6']
            grid6_time = dbcall[1]['grid6_time']

            # get C&IC and time info from other db for call
            caic_time = dbcall[1]['caic_time']
            caic_abbr = dbcall[1]['caic_abbr']
            caic_name = dbcall[1]['caic_name']

            qsop = dbcall[1]['qsop']

            gmt = datetime.datetime.fromtimestamp(lonlat_time, datetime.timezone.utc).strftime("%H:%M GMT")

            # has call not been seen in over age_out N seconds
            # if (time.time() - caic_time) > self.age_out:
            if (time.time() - lonlat_time) > self.age_out:
                # yes - del this call
                del db[call]
                continue

            # check if call is a registered or dynamic QSO Party station
            if qsop:
                filename = "qso-party.json"
            else:
                filename = "non-qso-party.json"

            # save off info to marker and backup files
            with open(wwwdir + filename, 'a') as f:
                if i[filename] > 0:
                    print(',', file=f)

                i[filename] += 1

                scall = re.sub("\-[\w\d]+", "", call)
                text = gmt + " - " + caic_abbr + " - " + caic_name

                print('{{"type":"Feature","properties":{{"id":"{}","icon":"{}","call":"{}","scall":"{}",'
                      '"text":"{}","qsop":"{}","caic_time":{},"caic_abbr":"{}","caic_name":"{}","grid6_time":{},'
                      '"grid6":"{}","lonlat_time":{}}},"geometry":{{"type":"Point",'
                      '"coordinates":[{:.5f},  {:.5f}]}}}}'.format(id, icon, call, scall, text, qsop, caic_time,
                                                                   caic_abbr, caic_name, grid6_time, grid6, lonlat_time,
                                                                   lon, lat), end='', file=f)

                id += 1
            f.close()

        with open(wwwdir + 'qso-party.json', 'a') as f:
            print('\n] }', file=f)
        f.close()

        with open(wwwdir + 'non-qso-party.json', 'a') as f:
            print('\n] }', file=f)
        f.close()

        return

    def writeCSV(self, db):
        # icon counter used by google maps
        icon = 1

        with open(wwwdir + 'table.csv', 'w') as f:
            calls = sorted(db.items(), key=lambda x: x[1]['lonlat_time'], reverse=True)
            # print(calls)

            print(f"{datetime.datetime.now():%m-%d-%Y,%H%M,GMT,SPOT}", file=f)

            print("QP CALL", "C&IC", "AGE", "AGE", sep=',', file=f)

            now = int(time.time())

            # loop for every call saved in hash
            for call in calls:
                # print(call)
                if not db[call[0]]['qsop']:
                    continue

                # caic_gmt = datetime.datetime.fromtimestamp(caic_time, datetime.timezone.utc)
                # geo_gmt = datetime.datetime.fromtimestamp(geo_time, datetime.timezone.utc)

                # get time recorded
                lonlat_time = db[call[0]]['lonlat_time']

                # get time in new C&IC
                caic_time = call[1]['caic_time']

                # has call not been seen in over age_out seconds
                # if (time.time() - caic_time) > self.age_out:
                if (time.time() - lonlat_time) > self.age_out:
                    # yes - del this call
                    del db[call[0]]
                    continue


                # print(geo_time, now)
                age_time = now - lonlat_time
                age_mins = int(age_time / 60)

                new_time = now - caic_time
                new_mins = int(new_time / 60)

                print(call[0], db[call[0]]['caic_abbr'], new_mins, age_mins, sep=',', file=f)

            print(",,,", end='', file=f)

            f.close()

        return


class geoBase():
    def __init__(self, opts, geoCB):
        self.runFile = None
        self.bndFile = None
        self.age_out = 14400
        self.callFile = None
        self.mode = 0  # 0 = APRS, 1 = replay

        # Setup Directories
        # Check for pyinstaller runtime
        if getattr(sys, 'frozen', False):
            self.appPath = sys._MEIPASS
        else:
            self.appPath = os.path.dirname(os.path.abspath(__file__))

        # Get standard directory for local files
        self.appDirs = AppDirs("QP-APRS-Tracker", "K1RA")
        try:
            os.makedirs(self.appDirs.user_config_dir, exist_ok=True)
        except:
            print("Error: Unable to create local log directory! [%s]" % self.appDirs.user_config_dir)
            exit(1)

        # Init filenames
        self.settingsFile = os.path.join(self.appDirs.user_config_dir, "config.ini")
        self.logFile = os.path.join(self.appDirs.user_config_dir, "run.log")
        self.aprsFile = os.path.join(self.appDirs.user_config_dir, "aprs.log")

        # Open logs
        self.initLogs()

        # Load settings
        self.config = ConfigParser()
        self.initSettings()
        self.readSettings()
        # process command line options if present
        self.cliSettings(opts)

        self.aprs = telnetlib.Telnet()

        try:
            host = self.config.get('APRS', 'host', fallback="noam.aprs2.net")
            tcp = self.config.get('APRS', 'tcp', fallback=14580)
            self.aprs_host = host
            self.aprs_port = tcp
            self.is_aprs_configured = 1
        except:
            self.SetStatusText("Configure APRS host")

        # Create geoDetector object
        self.geoDet = APRSGeoDetector(self.aprs_host, self.aprs_port, geoCB, self.age_out, self.logMain, self.logAPRS)

    def initLogs(self):
        # Main log
        try:
            formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
            handler = logging.handlers.RotatingFileHandler(self.logFile, maxBytes=1024 * 1024, backupCount=5)
            handler.setFormatter(formatter)

            consoleHandler = logging.StreamHandler(sys.stdout)
            consoleHandler.setFormatter(formatter)

            self.logMain = logging.getLogger("main")
            self.logMain.setLevel(logging.INFO)
            self.logMain.addHandler(handler)
            self.logMain.addHandler(consoleHandler)
        except:
            print("Error: Unable to initialize log file! [%s]" % self.logFile)
            exit(1)

        # APRS log
        try:
            formatter = logging.Formatter('%(message)s')
            handler = logging.FileHandler(self.aprsFile)
            handler.setFormatter(formatter)

            self.logAPRS = logging.getLogger("aprs")
            self.logAPRS.setLevel(logging.INFO)
            self.logAPRS.addHandler(handler)
        except:
            print("Error: Unable to initialize APRS log file! [%s]" % self.aprsFile)
            exit(1)

    def initSettings(self):
        # Create sections
        sects = ["BOUNDARY", "CALLS", "ALERTS", "APRS"]
        for sect in sects:
            if not self.config.has_section(sect):
                self.config.add_section(sect)

    def readSettings(self):
        self.config.read(self.settingsFile)

    def writeSettings(self):
        os.makedirs(self.appDirs.user_config_dir, exist_ok=True)
        with open(self.settingsFile, 'w') as configfile:
            self.config.write(configfile)

    def cliSettings(self, opts):
        # save opts if needed later
        self.opts = opts

        if opts.aprs:
            self.config.set('APRS', 'aprs', opts.aprs)

        if opts.tcp:
            self.config.set('APRS', 'tcp', opts.tcp)

        if opts.bndFile:
            if not os.path.isfile(opts.bndFile):
                print("Error: geographic boundary file not found [%s]\n" % opts.bndFile)
                parser.print_help()
                exit(1)
            else:
                print(opts.bndFile)
                self.config.set('BOUNDARY', 'file', opts.bndFile)
                self.bndFile = opts.bndFile

        if opts.callFile:
            if not os.path.isfile(opts.callFile):
                print("Error: QP calls file not found [%s]\n" % opts.callFile)
                parser.print_help()
                exit(1)
            else:
                self.config.set('CALLS', 'file', opts.callFile)
                self.callFile = opts.callFile

        if opts.runFile:
            if not os.path.isfile(opts.runFile):
                print("Error: APRS replay data file not found [%s]\n" % opts.runFile)
                parser.print_help()
                exit(1)
            else:
                self.mode = 1
                self.runFile = opts.runFile

        if opts.age_out:
            self.age_out = int(opts.age_out)
        else:
            self.age_out = 14400


class geoCLI(geoBase):
    def __init__(self, opts):
        print("QP-APRS-Tracker %s by K1RA" % VERSION)

        super().__init__(opts, self.geoCB)

        if self.bndFile:
            self.geoDet.loadBoundaries(self.bndFile)
        else:
            bnd = self.config.get('BOUNDARY', 'file', fallback=None)
            self.geoDet.loadBoundaries(bnd)

        if self.callFile:
            self.geoDet.loadCalls(self.callFile)
        else:
            callsfile = self.config.get('CALLS', 'file', fallback="qp-calls.txt")
            self.callFile = callsfile
            self.geoDet.loadCalls(callsfile)

        try:
            # Init APRS objects
            self.aprs_host = self.config.get('APRS', 'host', fallback="noam.aprs2.net")
            self.aprs_tcp = self.config.get('APRS', 'tcp', fallback=14580)
        except:
            print(
                "Error: APRS host parameters not provided! Configure through GUI mode or pass --host and --tcp "
                "parameters.")
            exit(1)

    def sigint(self, sig, frame):
        self.geoDet._do_exit = 1

    def run(self):
        # check for replay mode
        if self.mode == 1:
            self.geoDet.replayFile(self.runFile)
        else:
            signal.signal(signal.SIGINT, self.sigint)

            self.geoDet.mode = 1  # set cli mode for no idle state
            self.geoDet.state = 1  # skip idle and right to APRS open
            self.geoDet.run()

        # store any new settings from cli
        self.writeSettings()

    def geoCB(self, msg):
        (t, s) = msg


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("-c", "--cli", dest="cli",
                      action="store_true", default=False,
                      help="Run in command line mode")
    parser.add_option("-a", "--aprs", dest="aprs",
                      help="APRS hostname/IP address")
    parser.add_option("-t", "--tcp", dest="tcp",
                      help="APRS TCP port number")
    parser.add_option("-r", "--run", dest="runFile",
                      help="APRS data file for replay processing")
    parser.add_option("-b", "--boundary", dest="bndFile",
                      help="Geographic boundary kml data file")
    parser.add_option("-s", "--calls", dest="callFile",
                      help="QP calls data file")
    parser.add_option("-o", "--ageout", dest="age_out",
                      help="Age timeout for QP calls")

    (opts, args) = parser.parse_args()

    if opts.cli:
        # initiate console only mode
        app = geoCLI(opts)
        app.run()
