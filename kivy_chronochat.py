# -*- Mode:python; c-file-style:"gnu"; indent-tabs-mode:nil -*- */
#
# Copyright (C) 2014-2019 Regents of the University of California.
# Author: Jeff Thompson <jefft0@remap.ucla.edu>
# Derived from ChronoChat-js by Qiuhan Ding and Wentao Shang.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# A copy of the GNU Lesser General Public License is in the file COPYING.

# This include is produced by:
# protoc --python_out=. chatbuf.proto


import chatbuf_pb2
import threading
import sys
import logging
import time
import random
import select
import numpy
import string
from pyndn import Name
from pyndn import Interest
from pyndn import Data
from pyndn import Face
from pyndn.security import KeyChain
from pyndn.security import SafeBag
from pyndn.util import Blob
from pyndn.sync import ChronoSync2013
from functools import partial

from kivy.lang import Builder
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy import Config
Config.set('graphics', 'multisamples', '0') 
from kivy.utils import get_color_from_hex
import List
from List import MDList
from label import MDLabel
from kivy.uix.popup import Popup
from kivy.uix.image import AsyncImage
from kivy.clock import Clock
from navigationdrawer import NavigationDrawer
############
from os.path import expanduser
import os
import requests
global s
#######
global name

path_images = os.getcwd()
avail_image_extensions = ["*.jpg","*.png","*.gif","*.mp4"] #filter
avail_image_extensions_selection = [".jpg",".png",".gif",".mp4"]

# UI configuration
Builder.load_string("""
#:import get_color_from_hex __main__.get_color_from_hex
#:import path_images __main__.path_images
#:import avail_image_extensions __main__.avail_image_extensions

<Welcome>:
    username: username
    prefix: prefix
    chatroom: chatroom
    BoxLayout:
        orientation: 'vertical'
        padding: 30
        spacing: 30

        GridLayout:
            cols:2
            rows:3
            spacing: 10
            row_default_height: 30
            row_force_default: True        
                
            Label:
                text: 'Username:'
                halign: 'left'
                size_hint: (0.4, 1)
            TextInput:
                id: username
            Label:
                text: 'Prefix:'
                halign: 'left'
                size_hint: (0.4, 1)
            TextInput:
                id: prefix
            Label:
                text: 'Chatroom:'
                halign: 'left'
                size_hint: (0.4, 1)
            TextInput:
                id: chatroom
        Button:
            size: (30,30)
            text: 'Connect'
            on_release: 
                root.manager.current = "main_screen"
                root.manager.get_screen("main_screen").start_chat()

<ChatScreen>:       
    GridLayout:
        cols: 1
        rows: 0
        canvas:
            Color:
                rgba: get_color_from_hex("#ffffff")  
            Rectangle:
                pos: self.pos
                size: self.size
        ScrollView:
            do_scroll_x: False
            MDList:
                id: ml

    GridLayout:
        size_hint_y: None
        height: 40
        spacing: 15
        rows: 1
        cols: 2

        canvas:
            Color:
                rgba: (0.746,0.8,0.86,1)
            Rectangle:
                pos: self.pos
                size: self.size
        TextInput:
            id: message
            hint_text: "Type here"
            multiline: False
            on_text_validate:
                root.chat.sendMessage(message.text)
                root.refocusOnCommandTextInput()
        Button:
            text: "Attach"
            on_release:
                root.manager.current = "image_select_screen"

<ImageSelectScreen>:
    GridLayout:
        rows: 3
        cols: 1
        BoxLayout:
            size_hint_y: None
            Button:
                text: "Icon View"
                on_release: filechooser.view_mode = "icon"
            Button:
                text: "List View"
                on_release: filechooser.view_mode = "list"
        BoxLayout:
            canvas:
                Color:
                    rgba: get_color_from_hex("#000000")  
                Rectangle:
                    pos: self.pos
                    size: self.size
            FileChooser:
                id: filechooser
                path: path_images
                filters: avail_image_extensions
                on_selection: root.select(filechooser.selection)
                FileChooserIconLayout
                FileChooserListLayout
        BoxLayout:
            size_hint_y: None
            height: 30
            spacing: 10
            canvas:
                Color:
                    rgba: get_color_from_hex("#ffffff")  
                Rectangle:
                    pos: self.pos
                    size: self.size
            Button:
                text: "Send"
                on_release: root.send_it()
            Button:
                text: "Back"
                on_release: root.manager.current = "main_screen"


""")


# Define the Chat class here so that the ChronoChat demo is self-contained.
class Chat(object):
    def __init__(self, screenName, chatRoom, hubPrefix, face, keyChain,
      certificateName,messagelist,width,height):
        self._screenName = screenName
        self._chatRoom = chatRoom
        self._face = face
        self._keyChain = keyChain
        self._certificateName = certificateName
        self._messagelist = messagelist
        self._width = width
        self._height = height

        self._messageCache = [] # of CachedMessage
        self._media = ''
        self._mediacount = -1
        self._roster = [] # of str
        self._maxMessageCacheLength = 1000
        self._isRecoverySyncState = True
        self._syncLifetime = 5000.0 # milliseconds

        # This should only be called once, so get the random string here.
        self._chatPrefix = Name("/ndn/broadcast/").append(self._chatRoom).append("chat").append(
          self._getRandomString())
        session = int(round(self.getNowMilliseconds() / 1000.0))
        self._userName = self._screenName + str(session)

        self._sync = ChronoSync2013(
           self._sendInterest, self._initial, self._chatPrefix,
           Name("/ndn/broadcast/").append(hubPrefix), session,
           face, keyChain, certificateName, self._syncLifetime,
           onRegisterFailed)

        face.registerPrefix(self._chatPrefix, self._onInterest, onRegisterFailed)

    def sendMessage(self, chatMessage):
        """
        Send a chat message.
        """
        if len(self._messageCache) == 0:
            self._messageCacheAppend(chatbuf_pb2.ChatMessage.JOIN, "xxx", 0)

        # Ignore an empty message.
        # Forming Sync Data Packet.
        if chatMessage != "":
            self._sync.publishNextSequenceNo()
            self._messageCacheAppend(chatbuf_pb2.ChatMessage.CHAT, chatMessage, 0)
            # self._messagelist.insert(tk.END,self._screenName + ": " + chatMessage)
            self._messagelist.add_widget(List.TwoLineListItem(text=chatMessage,
            secondary_text=self._screenName,
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
            # print(self._screenName + ": " + chatMessage)

    def sendMultimediaMessage(self, chatMessage, finalblockId, filename):
        """
        Send a chat message.
        """
        if len(self._messageCache) == 0:
            self._messageCacheAppend(chatbuf_pb2.ChatMessage.JOIN, "xxx", 0)

        # Ignore an empty message.
        # Forming Sync Data Packet.
        if chatMessage != "":
            mediaparameter = str(finalblockId)+"-"+filename
            self._sync.publishNextSequenceNo()
            self._messageCacheAppend(chatbuf_pb2.ChatMessage.MEDIA, chatMessage, mediaparameter)
            # self._messagelist.insert(tk.END,self._screenName + ": " + chatMessage)
            # self._messagelist.add_widget(List.TwoLineListItem(text=chatMessage,
            # secondary_text=self._screenName,
            # markup=True,
            # text_size=(self._width,None),
            # size_hint_y=None,
            # font_size=(self._height / 23)))
            # print(self._screenName + ": " + chatMessage)

    def leave(self):
        """
        Send the leave message and leave.
        """
        self._sync.publishNextSequenceNo()
        self._messageCacheAppend(chatbuf_pb2.ChatMessage.LEAVE, "xxx", 0)

    @staticmethod
    def getNowMilliseconds():
        """
        Get the current time in milliseconds.

        :return: The current time in milliseconds since 1/1/1970, including
          fractions of a millisecond.
        :rtype: float
        """
        return time.time() * 1000.0

    def _initial(self):
        """
        Push the JOIN message in to the messageCache_, update roster
        and start the heartbeat.
        """
        # Set the heartbeat timeout using the Interest timeout mechanism. The
        # heartbeat() function will call itself again after a timeout.
        # TODO: Are we sure using a "/local/timeout" interest is the best future call
        # approach?
        timeout = Interest(Name("/local/timeout"))
        timeout.setInterestLifetimeMilliseconds(60000)
        self._face.expressInterest(timeout, self._dummyOnData, self._heartbeat)

        try:
           self._roster.index(self._userName)
        except ValueError:
            self._roster.append(self._userName)
            # self._messagelist.insert(tk.END,"Member: " + self._screenName)
            # self._messagelist.insert(tk.END,self._screenName + ": Join")
            self._messagelist.add_widget(List.TwoLineListItem(text="Join",
            secondary_text=self._screenName,
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
            # print("Member: " + self._screenName)
            # print(self._screenName + ": Join")
            self._messageCacheAppend(chatbuf_pb2.ChatMessage.JOIN, "xxx", 0)

    def _sendInterest(self, syncStates, isRecovery):
        """
        Send a Chat Interest to fetch chat messages after the user gets the Sync
        data packet back but will not send interest.
        """
        # This is used by _onData to decide whether to display the chat messages.
        self._isRecoverySyncState = isRecovery

        sendList = []       # of str
        sessionNoList = []  # of int
        sequenceNoList = [] # of int
        for j in range(len(syncStates)):
            syncState = syncStates[j]
            nameComponents = Name(syncState.getDataPrefix())
            tempName = nameComponents.get(-1).toEscapedString()
            sessionNo = syncState.getSessionNo()
            if not tempName == self._screenName:
                index = -1
                for k in range(len(sendList)):
                    if sendList[k] == syncState.getDataPrefix():
                        index = k
                        break

                if index != -1:
                    sessionNoList[index] = sessionNo
                    sequenceNoList[index] = syncState.getSequenceNo()
                else:
                    sendList.append(syncState.getDataPrefix())
                    sessionNoList.append(sessionNo)
                    sequenceNoList.append(syncState.getSequenceNo())

        for i in range(len(sendList)):
            uri = (sendList[i] + "/" + str(sessionNoList[i]) + "/" +
              str(sequenceNoList[i]))
            interest = Interest(Name(uri))
            interest.setInterestLifetimeMilliseconds(self._syncLifetime)
            self._face.expressInterest(interest, self._onData, self._chatTimeout)
            print interest.getName()

    def _onInterest(self, prefix, interest, face, interestFilterId, filter):
        """
        Send back a Chat Data Packet which contains the user's message.
        """
        content = chatbuf_pb2.ChatMessage()
        sequenceNo = int(
          interest.getName().get(self._chatPrefix.size() + 1).toEscapedString())
        gotContent = False
        for i in range(len(self._messageCache) - 1, -1, -1):
            message = self._messageCache[i]
            if message.sequenceNo == sequenceNo:
                if (message.messageType == chatbuf_pb2.ChatMessage.CHAT): 
                    # Use setattr because "from" is a reserved keyword.
                    setattr(content, "from", self._screenName)
                    content.to = self._chatRoom
                    content.type = message.messageType
                    content.data = message.message
                    content.timestamp = int(round(message.time / 1000.0))              
                elif (message.messageType == chatbuf_pb2.ChatMessage.MEDIA):
                    medianame = message.finalblock.split("-")[1]
                    mediafinalblock = int(message.finalblock.split("-")[0])
                    setattr(content, "from", self._screenName)
                    content.to = self._chatRoom
                    content.type = message.messageType
                    content.mediadata = message.message
                    content.timestamp = int(round(message.time / 1000.0))
                    content.finalblock = mediafinalblock
                    content.medianame = medianame
                else:
                    setattr(content, "from", self._screenName)
                    content.to = self._chatRoom
                    content.type = message.messageType
                    content.timestamp = int(round(message.time / 1000.0)) 

                gotContent = True
                break

        if gotContent:
            # TODO: Check if this works in Python 3.
            array = content.SerializeToString()
            data = Data(interest.getName())
            data.setContent(Blob(array))
            self._keyChain.sign(data, self._certificateName)
            try:
                face.putData(data)
            except Exception as ex:
                logging.getLogger(__name__).error(
                  "Error in transport.send: %s", str(ex))
                return

    def _onData(self, interest, data):
        """
        Process the incoming Chat data.
        """
        # TODO: Check if this works in Python 3.
        content = chatbuf_pb2.ChatMessage()
        content.ParseFromString(data.getContent().toBytes())

        if self.getNowMilliseconds() - content.timestamp * 1000.0 < 120000.0:
            # Use getattr because "from" is a reserved keyword.
            name = getattr(content, "from")
            prefix = data.getName().getPrefix(-2).toUri()
            sessionNo = int(data.getName().get(-2).toEscapedString())
            sequenceNo = int(data.getName().get(-1).toEscapedString())
            nameAndSession = name + str(sessionNo)

            l = 0
            # Update roster.
            while l < len(self._roster):
                entry = self._roster[l]
                tempName = entry[0:len(entry) - 10]
                tempSessionNo = int(entry[len(entry) - 10:])
                if (name != tempName and
                    content.type != chatbuf_pb2.ChatMessage.LEAVE):
                    l += 1
                else:
                    if name == tempName and sessionNo > tempSessionNo:
                        self._roster[l] = nameAndSession
                    break

            if l == len(self._roster):
                self._roster.append(nameAndSession)
                self._messagelist.add_widget(List.TwoLineListItem(text="Join",
            secondary_text=name,
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
                # print(name + ": Join")

            # Set the alive timeout using the Interest timeout mechanism.
            # TODO: Are we sure using a "/local/timeout" interest is the best
            # future call approach?
            timeout = Interest(Name("/local/timeout"))
            timeout.setInterestLifetimeMilliseconds(120000)
            self._face.expressInterest(
              timeout, self._dummyOnData,
              self._makeAlive(sequenceNo, name, str(sessionNo), prefix))

            # isRecoverySyncState_ was set by sendInterest.
            # TODO: If isRecoverySyncState_ changed, this assumes that we won't get
            #     data from an interest sent before it changed.
            # Use getattr because "from" is a reserved keyword.
            if (content.type == chatbuf_pb2.ChatMessage.CHAT and
                 not self._isRecoverySyncState and
                 getattr(content, "from") != self._screenName):
            	self._messagelist.add_widget(List.TwoLineListItem(text=content.data,
            secondary_text=getattr(content, "from"),
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
                # print(getattr(content, "from") + ": " + content.data)
            elif (content.type == chatbuf_pb2.ChatMessage.MEDIA and
                 getattr(content, "from") != self._screenName):
                self._media += str(content.mediadata)
                self._mediacount += 1
                print self._mediacount , content.finalblock
                if (self._mediacount == content.finalblock):
                    imgdata = numpy.fromstring(self._media, dtype='uint8')
                    fname = getattr(content, "from")+str(content.medianame)
                    f = open(fname,'wb')
                    f.write(self._media)
                    self._messagelist.add_widget(List.TwoLineListItem(text="Received file: "+fname + " from " + getattr(content, "from"),
            secondary_text=self._screenName,
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
                    self._media = ''
                    self._mediacount = -1
            elif content.type == chatbuf_pb2.ChatMessage.LEAVE:
                # leave message
                try:
                    n = self._roster.index(nameAndSession)
                    if name != self._screenName:
                        self._roster.pop(n)
                        self._messagelist.add_widget(List.TwoLineListItem(text="Leave",
            secondary_text=name,
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
                        # print(name + ": Leave")
                except ValueError:
                    pass

    @staticmethod
    def _chatTimeout(interest):
    	# self._messagelist.insert(tk.END,"Timeout waiting for chat data")
        print("Timeout waiting for chat data")

    def _heartbeat(self, interest):
        """
        This repeatedly calls itself after a timeout to send a heartbeat message
        (chat message type HELLO). This method has an "interest" argument
        because we use it as the onTimeout for Face.expressInterest.
        """
        if len(self._messageCache) == 0:
            self._messageCacheAppend(chatbuf_pb2.ChatMessage.JOIN, "xxx",0)

        self._sync.publishNextSequenceNo()
        self._messageCacheAppend(chatbuf_pb2.ChatMessage.HELLO, "xxx",0)

        # Call again.
        # TODO: Are we sure using a "/local/timeout" interest is the best future call
        # approach?
        timeout = Interest(Name("/local/timeout"))
        timeout.setInterestLifetimeMilliseconds(60000)
        self._face.expressInterest(timeout, self._dummyOnData, self._heartbeat)

    def _makeAlive(self, tempSequenceNo, name, sessionNo, prefix):
        """
        Return a function for onTimeout which calls _alive.
        """
        def f(interest):
            self._alive(interest, tempSequenceNo, name, sessionNo, prefix)
        return f

    def _alive(self, interest, tempSequenceNo, name, sessionNo, prefix):
        """
        This is called after a timeout to check if the user with prefix has a
        newer sequence number than the given tempSequenceNo. If not, assume the
        user is idle and remove from the roster and print a leave message. This
        method has an "interest" argument because we use it as the onTimeout for
        Face.expressInterest.
        """
        sequenceNo = self._sync.getProducerSequenceNo(prefix, sessionNo)
        nameAndSession = name + sessionNo
        try:
            n = self._roster.index(nameAndSession)
        except ValueError:
            n = -1

        if sequenceNo != -1 and n >= 0:
            if tempSequenceNo == sequenceNo:
                self._roster.pop(n)
                self._messagelist.add_widget(List.TwoLineListItem(text="Leave",
            secondary_text=name,
            markup=True,
            text_size=(self._width,None),
            size_hint_y=None,
            font_size=(self._height / 23)))
                # print(name + ": Leave")

    def _messageCacheAppend(self, messageType, message, finalblockId):
        """
        Append a new CachedMessage to messageCache_, using given messageType and
        message, the sequence number from _sync.getSequenceNo() and the current
        time. Also remove elements from the front of the cache as needed to keep
        the size to _maxMessageCacheLength.
        """
        self._messageCache.append(self._CachedMessage(
          self._sync.getSequenceNo(), messageType, message,
          self.getNowMilliseconds(),finalblockId))
        while len(self._messageCache) > self._maxMessageCacheLength:
          self._messageCache.pop(0)

    @staticmethod
    def _getRandomString():
        """
        Generate a random name for ChronoSync.
        """
        seed = "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM0123456789"
        result = ""
        for i in range(10):
          # Using % means the distribution isn't uniform, but that's OK.
          position = random.randrange(256) % len(seed)
          result += seed[position]

        return result

    @staticmethod
    def _dummyOnData(interest, data):
        """
        This is a do-nothing onData for using expressInterest for timeouts.
        This should never be called.
        """
        pass

    class _CachedMessage(object):
        def __init__(self, sequenceNo, messageType, message, time, finalblock):
            self.sequenceNo = sequenceNo
            self.messageType = messageType
            self.message = message
            self.time = time
            self.finalblock = finalblock


DEFAULT_RSA_PUBLIC_KEY_DER = bytearray([
    0x30, 0x82, 0x01, 0x22, 0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01,
    0x01, 0x05, 0x00, 0x03, 0x82, 0x01, 0x0f, 0x00, 0x30, 0x82, 0x01, 0x0a, 0x02, 0x82, 0x01, 0x01,
    0x00, 0xb8, 0x09, 0xa7, 0x59, 0x82, 0x84, 0xec, 0x4f, 0x06, 0xfa, 0x1c, 0xb2, 0xe1, 0x38, 0x93,
    0x53, 0xbb, 0x7d, 0xd4, 0xac, 0x88, 0x1a, 0xf8, 0x25, 0x11, 0xe4, 0xfa, 0x1d, 0x61, 0x24, 0x5b,
    0x82, 0xca, 0xcd, 0x72, 0xce, 0xdb, 0x66, 0xb5, 0x8d, 0x54, 0xbd, 0xfb, 0x23, 0xfd, 0xe8, 0x8e,
    0xaf, 0xa7, 0xb3, 0x79, 0xbe, 0x94, 0xb5, 0xb7, 0xba, 0x17, 0xb6, 0x05, 0xae, 0xce, 0x43, 0xbe,
    0x3b, 0xce, 0x6e, 0xea, 0x07, 0xdb, 0xbf, 0x0a, 0x7e, 0xeb, 0xbc, 0xc9, 0x7b, 0x62, 0x3c, 0xf5,
    0xe1, 0xce, 0xe1, 0xd9, 0x8d, 0x9c, 0xfe, 0x1f, 0xc7, 0xf8, 0xfb, 0x59, 0xc0, 0x94, 0x0b, 0x2c,
    0xd9, 0x7d, 0xbc, 0x96, 0xeb, 0xb8, 0x79, 0x22, 0x8a, 0x2e, 0xa0, 0x12, 0x1d, 0x42, 0x07, 0xb6,
    0x5d, 0xdb, 0xe1, 0xf6, 0xb1, 0x5d, 0x7b, 0x1f, 0x54, 0x52, 0x1c, 0xa3, 0x11, 0x9b, 0xf9, 0xeb,
    0xbe, 0xb3, 0x95, 0xca, 0xa5, 0x87, 0x3f, 0x31, 0x18, 0x1a, 0xc9, 0x99, 0x01, 0xec, 0xaa, 0x90,
    0xfd, 0x8a, 0x36, 0x35, 0x5e, 0x12, 0x81, 0xbe, 0x84, 0x88, 0xa1, 0x0d, 0x19, 0x2a, 0x4a, 0x66,
    0xc1, 0x59, 0x3c, 0x41, 0x83, 0x3d, 0x3d, 0xb8, 0xd4, 0xab, 0x34, 0x90, 0x06, 0x3e, 0x1a, 0x61,
    0x74, 0xbe, 0x04, 0xf5, 0x7a, 0x69, 0x1b, 0x9d, 0x56, 0xfc, 0x83, 0xb7, 0x60, 0xc1, 0x5e, 0x9d,
    0x85, 0x34, 0xfd, 0x02, 0x1a, 0xba, 0x2c, 0x09, 0x72, 0xa7, 0x4a, 0x5e, 0x18, 0xbf, 0xc0, 0x58,
    0xa7, 0x49, 0x34, 0x46, 0x61, 0x59, 0x0e, 0xe2, 0x6e, 0x9e, 0xd2, 0xdb, 0xfd, 0x72, 0x2f, 0x3c,
    0x47, 0xcc, 0x5f, 0x99, 0x62, 0xee, 0x0d, 0xf3, 0x1f, 0x30, 0x25, 0x20, 0x92, 0x15, 0x4b, 0x04,
    0xfe, 0x15, 0x19, 0x1d, 0xdc, 0x7e, 0x5c, 0x10, 0x21, 0x52, 0x21, 0x91, 0x54, 0x60, 0x8b, 0x92,
    0x41, 0x02, 0x03, 0x01, 0x00, 0x01
  ])

# Use an unencrypted PKCS #8 PrivateKeyInfo.
DEFAULT_RSA_PRIVATE_KEY_DER = bytearray([
    0x30, 0x82, 0x04, 0xbf, 0x02, 0x01, 0x00, 0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7,
    0x0d, 0x01, 0x01, 0x01, 0x05, 0x00, 0x04, 0x82, 0x04, 0xa9, 0x30, 0x82, 0x04, 0xa5, 0x02, 0x01,
    0x00, 0x02, 0x82, 0x01, 0x01, 0x00, 0xb8, 0x09, 0xa7, 0x59, 0x82, 0x84, 0xec, 0x4f, 0x06, 0xfa,
    0x1c, 0xb2, 0xe1, 0x38, 0x93, 0x53, 0xbb, 0x7d, 0xd4, 0xac, 0x88, 0x1a, 0xf8, 0x25, 0x11, 0xe4,
    0xfa, 0x1d, 0x61, 0x24, 0x5b, 0x82, 0xca, 0xcd, 0x72, 0xce, 0xdb, 0x66, 0xb5, 0x8d, 0x54, 0xbd,
    0xfb, 0x23, 0xfd, 0xe8, 0x8e, 0xaf, 0xa7, 0xb3, 0x79, 0xbe, 0x94, 0xb5, 0xb7, 0xba, 0x17, 0xb6,
    0x05, 0xae, 0xce, 0x43, 0xbe, 0x3b, 0xce, 0x6e, 0xea, 0x07, 0xdb, 0xbf, 0x0a, 0x7e, 0xeb, 0xbc,
    0xc9, 0x7b, 0x62, 0x3c, 0xf5, 0xe1, 0xce, 0xe1, 0xd9, 0x8d, 0x9c, 0xfe, 0x1f, 0xc7, 0xf8, 0xfb,
    0x59, 0xc0, 0x94, 0x0b, 0x2c, 0xd9, 0x7d, 0xbc, 0x96, 0xeb, 0xb8, 0x79, 0x22, 0x8a, 0x2e, 0xa0,
    0x12, 0x1d, 0x42, 0x07, 0xb6, 0x5d, 0xdb, 0xe1, 0xf6, 0xb1, 0x5d, 0x7b, 0x1f, 0x54, 0x52, 0x1c,
    0xa3, 0x11, 0x9b, 0xf9, 0xeb, 0xbe, 0xb3, 0x95, 0xca, 0xa5, 0x87, 0x3f, 0x31, 0x18, 0x1a, 0xc9,
    0x99, 0x01, 0xec, 0xaa, 0x90, 0xfd, 0x8a, 0x36, 0x35, 0x5e, 0x12, 0x81, 0xbe, 0x84, 0x88, 0xa1,
    0x0d, 0x19, 0x2a, 0x4a, 0x66, 0xc1, 0x59, 0x3c, 0x41, 0x83, 0x3d, 0x3d, 0xb8, 0xd4, 0xab, 0x34,
    0x90, 0x06, 0x3e, 0x1a, 0x61, 0x74, 0xbe, 0x04, 0xf5, 0x7a, 0x69, 0x1b, 0x9d, 0x56, 0xfc, 0x83,
    0xb7, 0x60, 0xc1, 0x5e, 0x9d, 0x85, 0x34, 0xfd, 0x02, 0x1a, 0xba, 0x2c, 0x09, 0x72, 0xa7, 0x4a,
    0x5e, 0x18, 0xbf, 0xc0, 0x58, 0xa7, 0x49, 0x34, 0x46, 0x61, 0x59, 0x0e, 0xe2, 0x6e, 0x9e, 0xd2,
    0xdb, 0xfd, 0x72, 0x2f, 0x3c, 0x47, 0xcc, 0x5f, 0x99, 0x62, 0xee, 0x0d, 0xf3, 0x1f, 0x30, 0x25,
    0x20, 0x92, 0x15, 0x4b, 0x04, 0xfe, 0x15, 0x19, 0x1d, 0xdc, 0x7e, 0x5c, 0x10, 0x21, 0x52, 0x21,
    0x91, 0x54, 0x60, 0x8b, 0x92, 0x41, 0x02, 0x03, 0x01, 0x00, 0x01, 0x02, 0x82, 0x01, 0x01, 0x00,
    0x8a, 0x05, 0xfb, 0x73, 0x7f, 0x16, 0xaf, 0x9f, 0xa9, 0x4c, 0xe5, 0x3f, 0x26, 0xf8, 0x66, 0x4d,
    0xd2, 0xfc, 0xd1, 0x06, 0xc0, 0x60, 0xf1, 0x9f, 0xe3, 0xa6, 0xc6, 0x0a, 0x48, 0xb3, 0x9a, 0xca,
    0x21, 0xcd, 0x29, 0x80, 0x88, 0x3d, 0xa4, 0x85, 0xa5, 0x7b, 0x82, 0x21, 0x81, 0x28, 0xeb, 0xf2,
    0x43, 0x24, 0xb0, 0x76, 0xc5, 0x52, 0xef, 0xc2, 0xea, 0x4b, 0x82, 0x41, 0x92, 0xc2, 0x6d, 0xa6,
    0xae, 0xf0, 0xb2, 0x26, 0x48, 0xa1, 0x23, 0x7f, 0x02, 0xcf, 0xa8, 0x90, 0x17, 0xa2, 0x3e, 0x8a,
    0x26, 0xbd, 0x6d, 0x8a, 0xee, 0xa6, 0x0c, 0x31, 0xce, 0xc2, 0xbb, 0x92, 0x59, 0xb5, 0x73, 0xe2,
    0x7d, 0x91, 0x75, 0xe2, 0xbd, 0x8c, 0x63, 0xe2, 0x1c, 0x8b, 0xc2, 0x6a, 0x1c, 0xfe, 0x69, 0xc0,
    0x44, 0xcb, 0x58, 0x57, 0xb7, 0x13, 0x42, 0xf0, 0xdb, 0x50, 0x4c, 0xe0, 0x45, 0x09, 0x8f, 0xca,
    0x45, 0x8a, 0x06, 0xfe, 0x98, 0xd1, 0x22, 0xf5, 0x5a, 0x9a, 0xdf, 0x89, 0x17, 0xca, 0x20, 0xcc,
    0x12, 0xa9, 0x09, 0x3d, 0xd5, 0xf7, 0xe3, 0xeb, 0x08, 0x4a, 0xc4, 0x12, 0xc0, 0xb9, 0x47, 0x6c,
    0x79, 0x50, 0x66, 0xa3, 0xf8, 0xaf, 0x2c, 0xfa, 0xb4, 0x6b, 0xec, 0x03, 0xad, 0xcb, 0xda, 0x24,
    0x0c, 0x52, 0x07, 0x87, 0x88, 0xc0, 0x21, 0xf3, 0x02, 0xe8, 0x24, 0x44, 0x0f, 0xcd, 0xa0, 0xad,
    0x2f, 0x1b, 0x79, 0xab, 0x6b, 0x49, 0x4a, 0xe6, 0x3b, 0xd0, 0xad, 0xc3, 0x48, 0xb9, 0xf7, 0xf1,
    0x34, 0x09, 0xeb, 0x7a, 0xc0, 0xd5, 0x0d, 0x39, 0xd8, 0x45, 0xce, 0x36, 0x7a, 0xd8, 0xde, 0x3c,
    0xb0, 0x21, 0x96, 0x97, 0x8a, 0xff, 0x8b, 0x23, 0x60, 0x4f, 0xf0, 0x3d, 0xd7, 0x8f, 0xf3, 0x2c,
    0xcb, 0x1d, 0x48, 0x3f, 0x86, 0xc4, 0xa9, 0x00, 0xf2, 0x23, 0x2d, 0x72, 0x4d, 0x66, 0xa5, 0x01,
    0x02, 0x81, 0x81, 0x00, 0xdc, 0x4f, 0x99, 0x44, 0x0d, 0x7f, 0x59, 0x46, 0x1e, 0x8f, 0xe7, 0x2d,
    0x8d, 0xdd, 0x54, 0xc0, 0xf7, 0xfa, 0x46, 0x0d, 0x9d, 0x35, 0x03, 0xf1, 0x7c, 0x12, 0xf3, 0x5a,
    0x9d, 0x83, 0xcf, 0xdd, 0x37, 0x21, 0x7c, 0xb7, 0xee, 0xc3, 0x39, 0xd2, 0x75, 0x8f, 0xb2, 0x2d,
    0x6f, 0xec, 0xc6, 0x03, 0x55, 0xd7, 0x00, 0x67, 0xd3, 0x9b, 0xa2, 0x68, 0x50, 0x6f, 0x9e, 0x28,
    0xa4, 0x76, 0x39, 0x2b, 0xb2, 0x65, 0xcc, 0x72, 0x82, 0x93, 0xa0, 0xcf, 0x10, 0x05, 0x6a, 0x75,
    0xca, 0x85, 0x35, 0x99, 0xb0, 0xa6, 0xc6, 0xef, 0x4c, 0x4d, 0x99, 0x7d, 0x2c, 0x38, 0x01, 0x21,
    0xb5, 0x31, 0xac, 0x80, 0x54, 0xc4, 0x18, 0x4b, 0xfd, 0xef, 0xb3, 0x30, 0x22, 0x51, 0x5a, 0xea,
    0x7d, 0x9b, 0xb2, 0x9d, 0xcb, 0xba, 0x3f, 0xc0, 0x1a, 0x6b, 0xcd, 0xb0, 0xe6, 0x2f, 0x04, 0x33,
    0xd7, 0x3a, 0x49, 0x71, 0x02, 0x81, 0x81, 0x00, 0xd5, 0xd9, 0xc9, 0x70, 0x1a, 0x13, 0xb3, 0x39,
    0x24, 0x02, 0xee, 0xb0, 0xbb, 0x84, 0x17, 0x12, 0xc6, 0xbd, 0x65, 0x73, 0xe9, 0x34, 0x5d, 0x43,
    0xff, 0xdc, 0xf8, 0x55, 0xaf, 0x2a, 0xb9, 0xe1, 0xfa, 0x71, 0x65, 0x4e, 0x50, 0x0f, 0xa4, 0x3b,
    0xe5, 0x68, 0xf2, 0x49, 0x71, 0xaf, 0x15, 0x88, 0xd7, 0xaf, 0xc4, 0x9d, 0x94, 0x84, 0x6b, 0x5b,
    0x10, 0xd5, 0xc0, 0xaa, 0x0c, 0x13, 0x62, 0x99, 0xc0, 0x8b, 0xfc, 0x90, 0x0f, 0x87, 0x40, 0x4d,
    0x58, 0x88, 0xbd, 0xe2, 0xba, 0x3e, 0x7e, 0x2d, 0xd7, 0x69, 0xa9, 0x3c, 0x09, 0x64, 0x31, 0xb6,
    0xcc, 0x4d, 0x1f, 0x23, 0xb6, 0x9e, 0x65, 0xd6, 0x81, 0xdc, 0x85, 0xcc, 0x1e, 0xf1, 0x0b, 0x84,
    0x38, 0xab, 0x93, 0x5f, 0x9f, 0x92, 0x4e, 0x93, 0x46, 0x95, 0x6b, 0x3e, 0xb6, 0xc3, 0x1b, 0xd7,
    0x69, 0xa1, 0x0a, 0x97, 0x37, 0x78, 0xed, 0xd1, 0x02, 0x81, 0x80, 0x33, 0x18, 0xc3, 0x13, 0x65,
    0x8e, 0x03, 0xc6, 0x9f, 0x90, 0x00, 0xae, 0x30, 0x19, 0x05, 0x6f, 0x3c, 0x14, 0x6f, 0xea, 0xf8,
    0x6b, 0x33, 0x5e, 0xee, 0xc7, 0xf6, 0x69, 0x2d, 0xdf, 0x44, 0x76, 0xaa, 0x32, 0xba, 0x1a, 0x6e,
    0xe6, 0x18, 0xa3, 0x17, 0x61, 0x1c, 0x92, 0x2d, 0x43, 0x5d, 0x29, 0xa8, 0xdf, 0x14, 0xd8, 0xff,
    0xdb, 0x38, 0xef, 0xb8, 0xb8, 0x2a, 0x96, 0x82, 0x8e, 0x68, 0xf4, 0x19, 0x8c, 0x42, 0xbe, 0xcc,
    0x4a, 0x31, 0x21, 0xd5, 0x35, 0x6c, 0x5b, 0xa5, 0x7c, 0xff, 0xd1, 0x85, 0x87, 0x28, 0xdc, 0x97,
    0x75, 0xe8, 0x03, 0x80, 0x1d, 0xfd, 0x25, 0x34, 0x41, 0x31, 0x21, 0x12, 0x87, 0xe8, 0x9a, 0xb7,
    0x6a, 0xc0, 0xc4, 0x89, 0x31, 0x15, 0x45, 0x0d, 0x9c, 0xee, 0xf0, 0x6a, 0x2f, 0xe8, 0x59, 0x45,
    0xc7, 0x7b, 0x0d, 0x6c, 0x55, 0xbb, 0x43, 0xca, 0xc7, 0x5a, 0x01, 0x02, 0x81, 0x81, 0x00, 0xab,
    0xf4, 0xd5, 0xcf, 0x78, 0x88, 0x82, 0xc2, 0xdd, 0xbc, 0x25, 0xe6, 0xa2, 0xc1, 0xd2, 0x33, 0xdc,
    0xef, 0x0a, 0x97, 0x2b, 0xdc, 0x59, 0x6a, 0x86, 0x61, 0x4e, 0xa6, 0xc7, 0x95, 0x99, 0xa6, 0xa6,
    0x55, 0x6c, 0x5a, 0x8e, 0x72, 0x25, 0x63, 0xac, 0x52, 0xb9, 0x10, 0x69, 0x83, 0x99, 0xd3, 0x51,
    0x6c, 0x1a, 0xb3, 0x83, 0x6a, 0xff, 0x50, 0x58, 0xb7, 0x28, 0x97, 0x13, 0xe2, 0xba, 0x94, 0x5b,
    0x89, 0xb4, 0xea, 0xba, 0x31, 0xcd, 0x78, 0xe4, 0x4a, 0x00, 0x36, 0x42, 0x00, 0x62, 0x41, 0xc6,
    0x47, 0x46, 0x37, 0xea, 0x6d, 0x50, 0xb4, 0x66, 0x8f, 0x55, 0x0c, 0xc8, 0x99, 0x91, 0xd5, 0xec,
    0xd2, 0x40, 0x1c, 0x24, 0x7d, 0x3a, 0xff, 0x74, 0xfa, 0x32, 0x24, 0xe0, 0x11, 0x2b, 0x71, 0xad,
    0x7e, 0x14, 0xa0, 0x77, 0x21, 0x68, 0x4f, 0xcc, 0xb6, 0x1b, 0xe8, 0x00, 0x49, 0x13, 0x21, 0x02,
    0x81, 0x81, 0x00, 0xb6, 0x18, 0x73, 0x59, 0x2c, 0x4f, 0x92, 0xac, 0xa2, 0x2e, 0x5f, 0xb6, 0xbe,
    0x78, 0x5d, 0x47, 0x71, 0x04, 0x92, 0xf0, 0xd7, 0xe8, 0xc5, 0x7a, 0x84, 0x6b, 0xb8, 0xb4, 0x30,
    0x1f, 0xd8, 0x0d, 0x58, 0xd0, 0x64, 0x80, 0xa7, 0x21, 0x1a, 0x48, 0x00, 0x37, 0xd6, 0x19, 0x71,
    0xbb, 0x91, 0x20, 0x9d, 0xe2, 0xc3, 0xec, 0xdb, 0x36, 0x1c, 0xca, 0x48, 0x7d, 0x03, 0x32, 0x74,
    0x1e, 0x65, 0x73, 0x02, 0x90, 0x73, 0xd8, 0x3f, 0xb5, 0x52, 0x35, 0x79, 0x1c, 0xee, 0x93, 0xa3,
    0x32, 0x8b, 0xed, 0x89, 0x98, 0xf1, 0x0c, 0xd8, 0x12, 0xf2, 0x89, 0x7f, 0x32, 0x23, 0xec, 0x67,
    0x66, 0x52, 0x83, 0x89, 0x99, 0x5e, 0x42, 0x2b, 0x42, 0x4b, 0x84, 0x50, 0x1b, 0x3e, 0x47, 0x6d,
    0x74, 0xfb, 0xd1, 0xa6, 0x10, 0x20, 0x6c, 0x6e, 0xbe, 0x44, 0x3f, 0xb9, 0xfe, 0xbc, 0x8d, 0xda,
    0xcb, 0xea, 0x8f
  ])

def onRegisterFailed(prefix):
    print("Register failed for prefix " + prefix.toUri())

def promptAndInput(prompt):
    if sys.version_info[0] <= 2:
        return raw_input(prompt)
    else:
        return input(prompt)

def chatcore(face,chat):
    while True:

        face.processEvents()
        # We need to sleep for a few milliseconds so we don't use 100% of the CPU.
        time.sleep(0.01)

    chat.leave()
    # Wait a little bit to allow other applications to fetch the leave message.
    startTime = Chat.getNowMilliseconds()
    while True:
        if Chat.getNowMilliseconds() - startTime >= 1000.0:
            break

        face.processEvents()
        time.sleep(0.01)

def chat_leave(chat):
	chat.leave()
	time.sleep(1.00)

def chat_start(face,chat):
    thread = threading.Thread(target = partial(chatcore,face,chat))
    thread.setDaemon(True)
    thread.start()

def chunkstring(string, length):
    return (string[0+i:length+i] for i in range(0, len(string), length))




class Welcome(Screen):
    def __init__(self,**kwargs):
        super(Welcome,self).__init__(**kwargs)


    def on_request_close(self):
        print "closecloseclose"

    def on_pre_enter(self):
        Window.size = (300,300)


class ChatScreen(Screen):
    global s
    def __init__(self,**kwargs):
        super(ChatScreen,self).__init__(**kwargs)
        Window.bind(on_request_close=self.exit_chat)
        self.ml = self.ids["ml"]
        self.chat = ''

    def exit_chat(self, *args):
        chat_leave(self.chat)

    def on_pre_enter(self):
        Window.size = (600,600)

    def refocusOnCommandTextInput(self):
        #defining a delay of 0.1 sec ensure the
        #refocus works in all situations. Leaving
        #it empty (== next frame) does not work
        #when pressing a button !
        self.ids.message.text = ''
        Clock.schedule_once(self._refocusTextInput, 0.1)       


    def _refocusTextInput(self, *args):
        self.ids.message.focus = True


    def start_chat(self):
        username = self.manager.get_screen("welcome_screen").username.text
        prefix = self.manager.get_screen("welcome_screen").prefix.text
        chatroom = self.manager.get_screen("welcome_screen").chatroom.text
        host = "localhost"
        face = Face(host)

        # Set up the key chain.
        keyChain = KeyChain("pib-memory:", "tpm-memory:")
        keyChain.importSafeBag(SafeBag
          (Name("/testname/KEY/123"),
           Blob(DEFAULT_RSA_PRIVATE_KEY_DER, False),
           Blob(DEFAULT_RSA_PUBLIC_KEY_DER, False)))
        face.setCommandSigningInfo(keyChain, keyChain.getDefaultCertificateName())

        self.chat = Chat(
          username, chatroom, Name(prefix), face, keyChain,
          keyChain.getDefaultCertificateName(),self.ml,self.width,self.height)

        chat_start(face,self.chat)

    def add_two_line(self,from_who,msg_to_add):

        self.ml.add_widget(List.TwoLineListItem(text=msg_to_add,
            secondary_text=from_who,
            markup=True,
            text_size=(self.width,None),
            size_hint_y=None,
            font_size=(self.height / 23)))

    # def on_enter(self):# only run this once, not everytime we switch back to it(main_screen)
    #     name = "admin"
    #     welcome = "omegalul"
    #     self.add_two_line("Admin",welcome)
    #     temp_template = {"name":name}
    #     thread = threading.Thread(target=self.handle_messages)
    #     thread.setDaemon(True)
    #     thread.start()

    def send_message(self,to_send_out):
        try:
            # if self.pvt_name.text != "":
            #     type_msg = "private_message"
            #     pvt_receiver = self.pvt_name.text
            # else:
            type_msg = "broadcast"
            pvt_receiver = ""

            template = {}
            template["msg_type"] = type_msg
            template["from"] = name
            template["msg"] = to_send_out
            template["pvt_receiver"] = pvt_receiver
            s.send(json.dumps(template))

        except Exception as e:
            print "Error sending: ",e


    def download_file_arbi(self, url):
        local_filename = url.split('/')[-1]
        # NOTE the stream=True parameter
        r = requests.get(url, stream=True)
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024): 
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    #f.flush() commented by recommendation from J.F.Sebastian
        return local_filename

    def handle_image_download(self, url_img):
        # create file downloader function for arbitrary files
        print "starting downlad"
        saved_img = self.download_file_arbi(url_img)
        self.add_two_line("self","File saved as "+saved_img)
        print "download complete"
        self.pop_image_saved(saved_img)
    def pop_image_saved(self, src):
        the_pic = AsyncImage(source=src)
        self.pop1(the_pic)

    def pop1(self,src):
        popup = Popup(title="Image loading",
                content=src)
        popup.open()

    def handle_messages(self):
        print "something"
        # while True:
        #     try:
        #         # data = json.loads(s.recv(1024))
        #         # if data["msg_type"] == "broadcast":
        #         #     #self.msg_log.text += data["from"] + " - " + data["msg"] + "\n"
        #         #     self.add_two_line(data["from"],data["msg"])

        #         # if data["msg_type"] == "image":
        #         #     #thread it
        #         #     threading.Thread(target=self.handle_image_download,args=(data["link"],)).start()

        #     except Exception as e:
        #         print e


class A:
    #class to return the name
    def get_the_name(self):
        return name

class ImageSelectScreen(Screen):

    def __init__(self,**kwargs):
        super(ImageSelectScreen,self).__init__(**kwargs)
        self.count = 0

    def select(self,filename):
        try:
            self.filename = filename[0]
            # self.preview_img(self.filename)
        except Exception as e:
            print e
    def preview_img(self, src):
        #do image popup    import popup & async image later
        popup = Popup(title="Preview",
                content=AsyncImage(source=src))
        popup.open()

    def upload_image(self, fname, urlll, some_dict):
        with open(fname, "rb") as f:
            files = {"testname": f}
            r = requests.post(urlll, files=files)#import requests
        s.send(json.dumps(some_dict))
        self.remove_file(fname)# delete the temp file

    def remove_file(self,fname):
        try:
            os.remove(fname)
            print "temp file removed"
        except Exception as e:
            print e
    def send_it(self):
        self.count +=1
        #this is upload part
        print "upload part"
        if len(self.filename) > 5:
            try:
                # host = "http://127.0.0.1/"
                # url_for_img = host + "man_images.php"
                # url_for_img_no_php = host + "img/"
                # print "inside"
                c_extension = os.path.splitext(self.filename)[1]# get file extension
                print c_extension
                if c_extension in avail_image_extensions_selection:
                    extesion = c_extension
                    #create temp file for randomness of filename
                    temp_img_file = str(self.count) + extesion
                    with open(self.filename, "rb") as f:
                        media = f.read()#read image
                        chunks = list(chunkstring(media,8192))

                        finalblock = len(chunks)-1
                        for i in range (0,len(chunks)):
                            self.manager.get_screen("main_screen").chat.sendMultimediaMessage(chunks[i],finalblock,temp_img_file)
                            time.sleep(0.08)
                    # with open(temp_img_file, "wb") as fb:
                    #     fb.write(orag)#write image to temp file

                    # link_img = url_for_img_no_php+temp_img_file
                    # some_dict = {
                    # "msg_type": "image",
                    # "link": link_img,
                    # "from": my_name
                    # }
                    # threading.Thread(target=self.upload_image, args=(temp_img_file, url_for_img, some_dict)).start()
                    sm.current = "main_screen"
                    self.manager.get_screen("main_screen").ml.add_widget(List.TwoLineListItem(text=temp_img_file+" sent",
            secondary_text=self.manager.get_screen("welcome_screen").username.text,
            markup=True,
            text_size=(self.manager.get_screen("main_screen").width,None),
            size_hint_y=None,
            font_size=(self.manager.get_screen("main_screen").height / 23)))
            except Exception as e:
                print e


class ChronoChatApp(App):
    def build(self):
        return sm


sm = ScreenManager()

sm.add_widget(Welcome(name="welcome_screen"))
sm.add_widget(ChatScreen(name="main_screen"))
sm.add_widget(ImageSelectScreen(name="image_select_screen"))

if __name__ == "__main__":
    ChronoChatApp().run()
