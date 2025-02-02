# ipop-project
# Copyright 2016, University of Florida
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from controller.framework.ControllerModule import ControllerModule
import socket,select,json,ast
import controller.framework.ipoplib as ipoplib
import controller.framework.fxlib as fxlib
from threading import Thread


class TincanInterface(ControllerModule):
    def __init__(self, CFxHandle, paramDict, ModuleName):
        super(TincanInterface, self).__init__(CFxHandle, paramDict, ModuleName)
        self.trans_counter = 0  # Counter to send transaction number for every TINCAN request
        self.TincanListenerThread = None    # Class data member to hold UDP listener Thread object
        # Check whether the system supports IPv6
        if socket.has_ipv6:
            self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            self.sock_svr = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            # Attribute to hold Controller UDP listening socket
            self.sock_svr.bind((self.CMConfig["localhost6"], self.CMConfig["ctrl_recv_port"]))
            # Attribute to hold Controller UDP sending socket
            self.dest = (self.CMConfig["localhost6"], self.CMConfig["ctrl_send_port"])
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock_svr = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Attribute to hold Controller UDP listening socket
            self.sock_svr.bind((self.CMConfig["localhost"], self.CMConfig["ctrl_recv_port"]))
            # Attribute to hold Controller UDP sending socket
            self.dest = (self.CMConfig["localhost"], self.CMConfig["ctrl_send_port"])
        self.sock.bind(("", 0))
        self.sock_list = [self.sock_svr]
        self.model = self.CFxHandle.queryParam('CFx', 'Model')

    def initialize(self):
        self.registerCBT('Logger', 'info', "{0} Loaded".format(self.ModuleName))
        # create a listener thread (listens to tincan notifications)
        self.TincanListenerThread = Thread(target=self.__tincan_listener)
        self.TincanListenerThread.setDaemon(True)
        self.TincanListenerThread.start()
        self.create_control_link()
        self.set_log_level()
        self.create_virtual_networks()
        self.set_ignored_interfaces()

    def __tincan_listener(self):
        while True:
            socks, _, _ = select.select(self.sock_list, [], [],
                                        self.CMConfig["SocketReadWaitTime"])
            # Iterate across all socket list to obtain Tincan messages
            for sock in socks:
                if sock == self.sock_svr:
                    data, addr = sock.recvfrom(self.CMConfig["buf_size"])
                    # Create CBT to process every Tincan message
                    self.registerCBT('TincanInterface', 'PROCESS_TINCAN_DATA', data)

    def processCBT(self, cbt):
        # CBT to process Link Creation
        if cbt.action == 'DO_CREATE_LINK':
            uid = cbt.data.get('uid')
            msg = cbt.data.get("data")
            connection_details = ipoplib.CONCT
            conn_details = connection_details["IPOP"]["Request"]
            conn_details["InterfaceName"] = cbt.data.get("interface_name")
            connection_details["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            conn_details["PeerInfo"]["VIP4"] = msg.get('ip4')
            conn_details["PeerInfo"]["UID"] = uid
            conn_details["PeerInfo"]["MAC"] = msg.get('mac')
            conn_details["PeerInfo"]["CAS"] = msg.get('cas')
            conn_details["PeerInfo"]["Fingerprint"] = msg.get('fpr')
            conn_details["Initiator"] = cbt.initiator
            self.send_msg(json.dumps(connection_details))
            self.registerCBT('Logger', 'debug', "Connection Details : {0}".format(str(conn_details)))
            self.registerCBT('Logger', 'info', "Creating Connection to Peer:{0}".format(uid))
        # CBT to process Link deletion request
        elif cbt.action == 'DO_TRIM_LINK':
            uid = cbt.data.get("uid")
            remove_node_details = ipoplib.REMOVE
            remove_node_details["IPOP"]["Request"]["InterfaceName"] = cbt.data.get("interface_name")
            remove_node_details["IPOP"]["Request"]["Initiator"] = cbt.initiator
            remove_node_details["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            remove_node_details["IPOP"]["Request"]["MAC"] = cbt.data.get("MAC")
            self.send_msg(json.dumps(remove_node_details))
            log = "Tincan Request : {0}".format(str(remove_node_details["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
            self.registerCBT('Logger', 'info', "Removing Connection to : {0}".format(uid))
        # CBT to process Query Link state
        elif cbt.action == 'DO_GET_STATE':
            get_state_request = ipoplib.LSTATE
            get_state_request["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            get_state_request["IPOP"]["Request"]["ProtocolVersion"] = 4
            get_state_request["IPOP"]["Request"]["InterfaceName"] = cbt.data.get("interface_name")
            get_state_request["IPOP"]["Request"]["UID"] = cbt.data.get("uid")
            get_state_request["IPOP"]["Request"]["MAC"] = cbt.data.get("MAC")
            get_state_request["IPOP"]["Request"]["Initiator"] = cbt.initiator
            self.send_msg(json.dumps(get_state_request))
            log = "Tincan Request: {0}".format(str(get_state_request["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
        # CBT to process GET CAS for a given peer MAC address
        elif cbt.action == 'DO_GET_CAS':
            lcas = ipoplib.LCAS
            data = cbt.data
            uid = data["uid"]
            lcas["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            lcas["IPOP"]["Request"]["InterfaceName"] = data["interface_name"]
            lcas["IPOP"]["Request"]["PeerInfo"]["VIP4"] = data["data"]["ip4"]
            lcas["IPOP"]["Request"]["PeerInfo"]["Fingerprint"] = data["data"]["fpr"]
            lcas["IPOP"]["Request"]["PeerInfo"]["UID"] = uid
            lcas["IPOP"]["Request"]["PeerInfo"]["MAC"] = data["data"]["mac"]
            lcas["IPOP"]["Request"]["Initiator"] = cbt.initiator
            self.registerCBT('Logger', 'debug', "Get CAS Request: {0}".format(str(lcas["IPOP"])))
            self.send_msg(json.dumps(lcas))
        # CBT message to keep Tincan and controller channel up and running
        elif cbt.action == 'DO_ECHO':
            ec = ipoplib.ECHO
            ec["IPOP"]["Request"]["InterfaceName"] = cbt.data.get("interface_name")
            ec["IPOP"]["Request"]["TransactionId"] = self.trans_counter
            ec["IPOP"]["Request"]["Initiator"] = cbt.initiator
            self.trans_counter += 1
            self.send_msg(json.dumps(ec))
        # CBT to send ICC message via overlay
        elif cbt.action == 'DO_SEND_ICC_MSG':
            icc_message_details = ipoplib.ICC
            icc_message_details["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            icc_message_details["IPOP"]["Request"]["InterfaceName"] = cbt.data.get("interface_name")
            icc_message_details["IPOP"]["Request"]["Recipient"] = cbt.data.get('dst_uid')
            icc_message_details["IPOP"]["Request"]["RecipientMac"] = cbt.data.get('dst_mac')
            msg = cbt.data.get("msg")
            icc_message_details["IPOP"]["Request"]["Data"] = json.dumps(msg)
            icc_message_details["IPOP"]["Request"]["Initiator"] = cbt.initiator
            self.send_msg(json.dumps(icc_message_details))
            log = "Sending ICC Message: {0}".format(str(icc_message_details["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
        # CBT to process request to insert data into the local network interface
        elif cbt.action == 'DO_INSERT_DATA_PACKET':
            packet = ipoplib.INSERT_TAP_PACKET
            packet["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            packet["IPOP"]["Request"]["InterfaceName"] = cbt.data["interface_name"]
            packet["IPOP"]["Request"]["Data"] = cbt.data["dataframe"]
            self.send_msg(json.dumps(packet))
            log = "Inserting Network Packet: {0}".format(str(packet["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
        # CBT to retry any Tincan Request
        #elif cbt.action == 'DO_RETRY':
        #    self.send_msg(json.dumps(cbt.data))
        # CBT to process request to insert Forwarding rule in Tincan
        elif cbt.action == "DO_INSERT_FORWARDING_RULES":
            add_routing = ipoplib.ADD_FORWARDING_RULE
            add_routing["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            add_routing["IPOP"]["Request"]["InterfaceName"] = cbt.data["interface_name"]
            add_routing["IPOP"]["Request"]["Routes"] = []
            sourcemac = cbt.data["sourcemac"]
            for mac in cbt.data.get("destmac"):
                if mac != "0" * 12 and mac != sourcemac:
                    add_routing["IPOP"]["Request"]["Routes"] = [mac + ":" + sourcemac]
                    log = "Inserting Routing Rule: {0}".format(str(add_routing["IPOP"]))
                    self.registerCBT('Logger', 'debug', log)
                    self.send_msg(json.dumps(add_routing))
        # CBT to process request to remove Forwarding rule in Tincan
        elif cbt.action == "DO_REMOVE_FORWARDING_RULES":
            remove_routing = ipoplib.DELETE_FORWARDING_RULE
            remove_routing["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            remove_routing["IPOP"]["Request"]["InterfaceName"] = cbt.data["interface_name"]
            remove_routing["IPOP"]["Request"]["Routes"] = [cbt.data["mac"]]
            log = "Routing Rule Removed: {0}".format(str(remove_routing["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
            self.send_msg(json.dumps(remove_routing))
        # CBT to process request to send any message to Tincan
        elif cbt.action == "DO_SEND_TINCAN_MSG":
            data = cbt.data
            data["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            data["IPOP"]["Request"]["Initiator"] = cbt.initiator
            self.send_msg(json.dumps(data))
            log = "Data sent to Tincan: {0}".format(str(data))
            self.registerCBT('Logger', 'debug', log)
        elif cbt.action == 'DO_QUERY_LINK_STATS':
            link_stat_request = ipoplib.LINK_STATS
            link_stat_request["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            link_stat_request["IPOP"]["Request"]["ProtocolVersion"] = 4
            link_stat_request["IPOP"]["Request"]["InterfaceName"] = cbt.data.get("interface_name")
            link_stat_request["IPOP"]["Request"]["UID"] = cbt.data.get("uid")
            link_stat_request["IPOP"]["Request"]["MAC"] = cbt.data.get("MAC")
            link_stat_request["IPOP"]["Request"]["Initiator"] = cbt.initiator
            link_stat_request["IPOP"]["Owner"] = cbt.initiator
            self.send_msg(json.dumps(link_stat_request))
            log = "Tincan Request: {0}".format(str(link_stat_request["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
        elif cbt.action == 'DO_QUERY_ADDRESS_SET':
            query_cas_request = ipoplib.QUERY_CAS
            query_cas_request["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            query_cas_request["IPOP"]["Request"]["ProtocolVersion"] = 4
            query_cas_request["IPOP"]["Request"]["InterfaceName"] = cbt.data.get("interface_name")
            query_cas_request["IPOP"]["Request"]["UID"] = cbt.data.get("uid")
            query_cas_request["IPOP"]["Request"]["MAC"] = cbt.data.get("MAC")
            query_cas_request["IPOP"]["Request"]["Initiator"] = cbt.initiator
            query_cas_request["IPOP"]["Owner"] = cbt.initiator
            self.send_msg(json.dumps(query_cas_request))
            log = "Tincan Request: {0}".format(str(query_cas_request["IPOP"]))
            self.registerCBT('Logger', 'debug', log)
        # CBT to process messages from Tincan
        elif cbt.action == "PROCESS_TINCAN_DATA":
            interface_name, data = "", cbt.data
            tincan_resp_msg = json.loads(data.decode("utf-8"))["IPOP"]
            # Extract the Operation from the Tincan message
            req_operation = tincan_resp_msg["Request"]["Command"]

            # Check if tap name exits in the TINCAN Response Message
            if "InterfaceName" in tincan_resp_msg["Request"].keys():
                interface_name = tincan_resp_msg["Request"]["InterfaceName"]

            # Condition to check if Tincan Message not an UpdateRoute or an ICC Message
            if "Response" in tincan_resp_msg.keys():
                # check whether the Tincan response is Success message
                if tincan_resp_msg["Response"]["Success"] is True:
                    # Whether the response is for GET_NODE_STATE operation
                    if req_operation == "QueryNodeInfo":
                        resp_msg = json.loads(tincan_resp_msg["Response"]["Message"])
                        resp_target_module = tincan_resp_msg["Request"]["Initiator"]
                        # Check whether the Query is for Self or a remote node
                        if resp_msg["Type"] == "local":
                            msg = {
                                "type": "local_state",
                                "_uid": resp_msg["UID"],
                                "ip4": resp_msg["VIP4"],
                                "fpr": resp_msg["Fingerprint"],
                                "mac": resp_msg["MAC"],
                                "interface_name": interface_name
                            }
                            log = "current state of {0} : {1}".format(resp_msg["UID"], str(msg))
                            self.registerCBT('Logger', 'debug', log)
                            self.registerCBT(resp_target_module, 'TINCAN_RESPONSE', msg)
                        else:
                            # Checks whether the link to peer is in Unknown state
                            if resp_msg["Status"] != "unknown":
                                msg = {
                                    "type": "peer_state",
                                    "uid": tincan_resp_msg["Request"]["UID"],
                                    "ip4": resp_msg["VIP4"],
                                    "fpr": resp_msg["Fingerprint"],
                                    "mac": resp_msg["MAC"],
                                    "status": resp_msg["Status"],
                                    "interface_name": interface_name
                                }
                            else:
                                msg = {
                                    "type": "peer_state",
                                    "uid": tincan_resp_msg["Request"]["UID"],
                                    "ip4": "",
                                    "fpr": "",
                                    "mac": "",
                                    "ttl": "",
                                    "rate": "",
                                    "status": resp_msg["Status"],
                                    "interface_name": interface_name
                                }
                            log = "Peer UID:{0} State:{1}".format(tincan_resp_msg["Request"]["UID"], resp_msg["Status"])
                            self.registerCBT('Logger', 'debug', log)
                            self.registerCBT(resp_target_module, 'TINCAN_RESPONSE', msg)
                    # Whether the response is for DO_GET_CAS operation
                    elif req_operation == "CreateTunnel":
                        # Sends the CAS to LinkManager
                        resp_target_module = tincan_resp_msg["Request"]["Initiator"]
                        log = "Received data from Tincan for operation: {0}. Data: {1}".\
                            format(tincan_resp_msg["Request"]["Command"], str(tincan_resp_msg))
                        self.registerCBT('Logger', 'info', log)
                        msg = {
                            "uid": tincan_resp_msg["Request"]["PeerInfo"]["UID"],
                            "data": {
                                "fpr": tincan_resp_msg["Request"]["PeerInfo"]["Fingerprint"],
                                "cas": tincan_resp_msg['Response']['Message'],
                                "peer_mac": tincan_resp_msg["Request"]["PeerInfo"]["MAC"]
                            },
                            "interface_name": interface_name
                        }
                        self.registerCBT(resp_target_module, 'SEND_CAS_DETAILS_TO_PEER', msg)
                    elif req_operation == "ConnectTunnel":
                        # Response message for Connection Request for a p2plink
                        log = "Received data from Tincan for operation: {0} Data: {1}".format\
                            (tincan_resp_msg["Request"]["Command"], str(tincan_resp_msg))
                        self.registerCBT('Logger', 'debug', log)
                        msg = {
                            "type": "con_resp",
                            "uid": tincan_resp_msg["Request"]["PeerInfo"]["UID"],
                            "data": {
                                "fpr": tincan_resp_msg["Request"]["PeerInfo"]["Fingerprint"],
                                "cas": tincan_resp_msg["Request"]["PeerInfo"]["CAS"],
                            },
                            "status": "offline",
                            "interface_name": interface_name
                        }
                        return
                    elif req_operation == "QueryCandidateAddressSet":
                        resp_msg = json.loads(tincan_resp_msg["Response"]["Message"])
                        resp_target_module = tincan_resp_msg["Request"]["Initiator"]
                        if "Controlled" in resp_msg.keys():
                            cas  = str(resp_msg["Controlled"])
                            if cas.find("stun") != -1:
                                msg = {
                                    "interface_name": interface_name,
                                    "cas": cas,
                                    "type": "set_geo_ip"
                                } #FixMe
                                self.registerCBT(resp_target_module, 'TINCAN_RESPONSE', msg)
                                return
                        elif "Controlling" in resp_msg.keys():
                            cas  = str(resp_msg["Controlling"])
                            if cas.find("stun") != -1:
                                msg = {
                                    "interface_name": interface_name,
                                    "cas": cas,
                                    "type": "set_geo_ip"
                                }  #FixMe
                                self.registerCBT(resp_target_module, 'TINCAN_RESPONSE', msg)
                                return
                    elif req_operation == "QueryLinkStats":
                        resp_msg = json.loads(tincan_resp_msg["Response"]["Message"])
                        resp_target_module = tincan_resp_msg["Request"]["Initiator"]
                        self.registerCBT('Logger', 'info', json.dumps(resp_msg))
                        return # Fix Me - LinkManager not coded to recieve Tunnel Stats
                        self.registerCBT(resp_target_module, 'TINCAN_RESPONSE', resp_msg)
                    elif req_operation in ["CreateCtrlRespLink", "ConfigureLogging", "CreateVnet",
                                           "SetIgnoredNetInterfaces", "RemovePeer"]:
                        self.registerCBT("Logger", "info", "Received data from Tincan: Operation: {0}."
                                                          " Task status::{1}".format(req_operation,
                                                                                     tincan_resp_msg["Response"]))
                        return
                    else:
                        log = '{0}: unrecognized Data {1} received from {2}. Data:::{3}' \
                            .format(cbt.recipient, cbt.action, cbt.initiator, cbt.data)
                        self.registerCBT('Logger', 'warning', log)
                else:
                    log = 'Tincan Failure Status for request:: '.format(cbt.data)
                    self.registerCBT('Logger', 'warning', log)
            else:
                # Checks whether the message is an ICC message
                if req_operation == "ICC":
                    iccmsg = json.loads(tincan_resp_msg["Request"]["Data"])
                    self.registerCBT('Logger', 'debug', "ICC Message Received ::" + str(iccmsg))
                    if "msg" in iccmsg.keys():
                        iccmsg["msg"]["type"] = "remote"
                        iccmsg["msg"]["interface_name"] = tincan_resp_msg["Request"]["InterfaceName"]
                        if "message_type" in iccmsg["msg"]:
                            # Check whether data routed is Packetdata
                            if iccmsg["msg"]["message_type"] == "BroadcastPkt":
                                dataframe = iccmsg["msg"]["dataframe"]
                                # Check whether the Packet is ARP Packet
                                if dataframe[24:28] == "0806":
                                    self.registerCBT('ArpCache', 'ARPPacket', iccmsg["msg"])
                                # Check whether packet is IPv4 Multicast Packet
                                #elif dataframe[0:6] == "01005E":
                                #    self.registerCBT('IPMulticast', 'IPv4_MULTICAST', iccmsg["msg"])
                                # Check whether packet is IPv6 Multicast Packet
                                #elif dataframe[0:4] == "3300":
                                #    self.registerCBT('IPMulticast', 'IPv6_MULTICAST', iccmsg["msg"])
                                else:
                                    # Broadcast other packets
                                    self.registerCBT('BroadcastForwarder', 'BroadcastPkt', iccmsg["msg"])
                            # Check whether data is Control data
                            elif iccmsg["msg"]["message_type"] == "BroadcastData":
                                # Convert string control data to dictionary
                                iccmessage = ast.literal_eval(iccmsg["msg"]["dataframe"])
                                iccmessage["interface_name"] = tincan_resp_msg["Request"]["InterfaceName"]
                                # Check the control data message type so that it routes to appropriate module
                                if iccmessage["message_type"] == "SendMacDetails":
                                    self.registerCBT('ArpCache', 'PeerMACIPDetails', iccmessage)
                                self.registerCBT('BroadcastForwarder', 'BroadcastData', iccmsg["msg"])
                            else:
                                self.registerCBT('BaseTopologyManager', 'ICC_CONTROL', iccmsg["msg"])
                        else:
                            self.registerCBT('BroadcastForwarder', 'BroadcastData', iccmsg["msg"])
                    else:
                        # Pass all non routing messages to BTM
                        iccmsg["interface_name"] = tincan_resp_msg["Request"]["InterfaceName"]
                        self.registerCBT('BaseTopologyManager', 'ICC_CONTROL', iccmsg)

                elif req_operation == "UpdateRoutes":
                    msg = tincan_resp_msg["Request"]["Data"]
                    interface_name = tincan_resp_msg["Request"]["InterfaceName"]
                    # Create message for inter module communication within the controller
                    datagram = {
                        "dataframe": msg,
                        "interface_name": interface_name,
                        "type": "local"
                    }

                    log = "Tincan Packet received ::{0}".format(datagram)
                    self.registerCBT('Logger', 'debug', log)
                    # Check for IPv4 and IPv6 Packet, if YES send it to BTM for processing
                    if str(msg[24:28]) in ["0800", "86DD"]:
                        datagram["m_type"] = "IP"
                        self.registerCBT("BaseTopologyManager", "TINCAN_PACKET", datagram)
                    # Check whether Packet is ARP message then route to ARPManager
                    elif str(msg[24:28]) == "0806":
                        datagram["m_type"] = "ARP"
                        self.registerCBT('ArpCache', 'ARPPacket', datagram)
                    # Send all other Packets for Broadcast
                    else:
                        datagram["message_type"] = "BroadcastPkt"
                        self.registerCBT('BroadcastForwarder', 'BroadcastPkt', datagram)
                else:
                    log = '{0}: unrecognized Data {1} received from {2}. Data:::{3}' \
                        .format(cbt.recipient, cbt.action, cbt.initiator, cbt.data)
                    self.registerCBT('Logger', 'warning', log)
        else:
            log = '{0}: unrecognized CBT {1} received from {2}'\
                    .format(cbt.recipient, cbt.action, cbt.initiator)
            self.registerCBT('Logger', 'warning', log)

    def send_msg(self, msg):
        return self.sock.sendto(bytes(msg.encode('utf-8')), self.dest)

    def timer_method(self):
        pass

    def terminate(self):
        pass
    '''
    Instructs Tincan to create the UDP control connection for sending message to the controller
    '''
    def create_control_link(self,):
        self.registerCBT("Logger", "info", "Creating Tincan control response link")
        ep = ipoplib.RESPLINK
        if self.CMConfig["ctrl_recv_port"] is not None:
          ep["IPOP"]["Request"]["Port"] = self.CMConfig["ctrl_recv_port"]
        if socket.has_ipv6 is False:
            ep["IPOP"]["Request"]["AddressFamily"] = "af_inet"
            ep["IPOP"]["Request"]["IP"] = self.CMConfig["localhost"]
        else:
            ep["IPOP"]["Request"]["AddressFamily"] = "af_inetv6"
            ep["IPOP"]["Request"]["IP"] = self.CMConfig["localhost6"]
        ep["IPOP"]["TransactionId"] = self.trans_counter
        self.trans_counter += 1
        self.send_msg(json.dumps(ep))

    '''
    Set Tincan's Logging Level
    '''
    def set_log_level(self,):
        log_level = self.CFxHandle.queryParam("Logger", "LogLevel")
        self.registerCBT("Logger", "info", "Setting Tincan log level to " + log_level)
        lgl = ipoplib.LOGCFG
        lgl["IPOP"]["Request"]["Level"] = log_level
        lgl["IPOP"]["Request"]["Device"] = self.CFxHandle.queryParam("Logger", "LogOption")
        lgl["IPOP"]["Request"]["Directory"] = self.CFxHandle.queryParam("Logger", "LogFilePath")
        lgl["IPOP"]["Request"]["Filename"] = self.CFxHandle.queryParam("Logger", "TincanLogFileName")
        lgl["IPOP"]["Request"]["MaxArchives"] = self.CFxHandle.queryParam("Logger", "BackupLogFileCount")
        lgl["IPOP"]["Request"]["MaxFileSize"] = self.CFxHandle.queryParam("Logger", "LogFileSize")
        lgl["IPOP"]["Request"]["ConsoleLevel"] = self.CFxHandle.queryParam("Logger", "ConsoleLevel")
        lgl["IPOP"]["TransactionId"] = self.trans_counter
        self.trans_counter += 1
        self.send_msg(json.dumps(lgl))

    '''
    Create the virtual network specfied in the config 
    '''
    def create_virtual_networks(self,):
        for i in range(len(self.CMConfig["Vnets"])):
            vnetdetails = self.CMConfig["Vnets"][i]
            vn = ipoplib.VNET
            # Create VNET Request Message
            self.registerCBT("Logger", "info", "Creating Vnet {0}".format(vnetdetails["TapName"]))
            vn["IPOP"]["Request"]["InterfaceName"] = vnetdetails["TapName"]
            vn["IPOP"]["Request"]["Description"] = vnetdetails["Description"]
            vn["IPOP"]["Request"]["LocalVirtIP4"] = vnetdetails["IP4"]
            vn["IPOP"]["Request"]["LocalPrefix4"] = vnetdetails["IP4PrefixLen"]
            if "MTU4" in vnetdetails:
                vn["IPOP"]["Request"]["MTU4"] = vnetdetails["MTU4"]
            vnetdetails["uid"] = fxlib.gen_uid(vnetdetails["IP4"])
            vn["IPOP"]["Request"]["LocalUID"] = vnetdetails["uid"]
            # Currently configured to take the first stun address
            vn["IPOP"]["Request"]["StunAddress"] = self.CMConfig["Stun"][0]
            if "Turn" in self.CMConfig:
                if self.CMConfig["Turn"][0]["Address"] is not None:
                    vn["IPOP"]["Request"]["TurnAddress"] = self.CMConfig["Turn"][0]["Address"]
                if self.CMConfig["Turn"][0]["User"] is not None:
                    vn["IPOP"]["Request"]["TurnUser"] = self.CMConfig["Turn"][0]["User"]
                if self.CMConfig["Turn"][0]["Password"] is not None:
                    vn["IPOP"]["Request"]["TurnPass"] = self.CMConfig["Turn"][0]["Password"]
            if "IPMappingEnabled" in vnetdetails:
                vn["IPOP"]["Request"]["IPMappingEnabled"] = vnetdetails["IPMappingEnabled"]
            vn["IPOP"]["Request"]["L2TunnelEnabled"] = True
            vn["IPOP"]["TransactionId"] = self.trans_counter
            self.trans_counter += 1
            self.send_msg(json.dumps(vn))

    '''
    Network Interfaces that will not be used for tunneling
    '''
    def set_ignored_interfaces(self,):
        for i in range(len(self.CMConfig["Vnets"])):
            vnetdetails = self.CMConfig["Vnets"][i]
            self.registerCBT("Logger", "info", "Ignoring interfaces {0}".
                              format(vnetdetails["IgnoredNetInterfaces"]))
            if "IgnoredNetInterfaces" in vnetdetails:
                net_ignore_list = ipoplib.IGNORE
                net_ignore_list["IPOP"]["Request"]["IgnoredNetInterfaces"] = vnetdetails["IgnoredNetInterfaces"]
                net_ignore_list["IPOP"]["Request"]["InterfaceName"] = vnetdetails["TapName"]
                net_ignore_list["IPOP"]["TransactionId"] = self.trans_counter
                self.trans_counter += 1
                self.send_msg(json.dumps(net_ignore_list))
