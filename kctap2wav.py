# -*- coding: utf-8 -*-
"""
Created on Sun Feb 12 16:45:48 2017

@author: palazzol
"""

# Convert .tap file to .wav

import argparse
import sys
import wave

class KCFile:
    def __init__(self):
        parser = argparse.ArgumentParser(description='Decode KC tap file to wav.')
        parser.add_argument('infile', type=argparse.FileType('rb'), help='Input file to decode')
        parser.add_argument('outfile', type=argparse.FileType('wb'), help='Output file')
        self.args = parser.parse_args()
    
    def Handle(self, sign, data, present, bit):
        mag = 30000
        if present == 0:
            data.append(0)
            data.append(0)
        elif bit == 0:
            sign = -sign;
            data.append(sign*mag)
            data.append(sign*mag)
        else:
            data.append(-sign*mag)
            data.append(sign*mag)
        return sign

    def BuildFrame(self, frame, newvals):
        for newval in newvals:
            frame = frame + newval.to_bytes(2, byteorder='little', signed=True)
        return frame
        
    def Process(self):

        ww = wave.Wave_write(self.args.outfile)
    
        ww.setnchannels(2)
        ww.setframerate(6000)
        ww.setsampwidth(2)
        
        rawdata = self.args.infile.read(2)
        sign0 = 1
        sign1 = 1
        while len(rawdata) == 2:
            data0 = []
            data1 = []
            sign0 = self.Handle(sign0, data0, rawdata[0] & 0x80, rawdata[0] & 0x40)
            sign1 = self.Handle(sign1, data1, rawdata[1] & 0x80, rawdata[1] & 0x40)
            sign0 = self.Handle(sign0, data0, rawdata[0] & 0x20, rawdata[0] & 0x10)
            sign1 = self.Handle(sign1, data1, rawdata[1] & 0x20, rawdata[1] & 0x10)
            sign0 = self.Handle(sign0, data0, rawdata[0] & 0x08, rawdata[0] & 0x04)
            sign1 = self.Handle(sign1, data1, rawdata[1] & 0x08, rawdata[1] & 0x04)
            sign0 = self.Handle(sign0, data0, rawdata[0] & 0x02, rawdata[0] & 0x01)
            sign1 = self.Handle(sign1, data1, rawdata[1] & 0x02, rawdata[1] & 0x01)
                            
            frame = bytearray([])
            frame = self.BuildFrame(frame,[x for t in zip(data0, data1) for x in t]) 
            ww.writeframes(frame)
            
            rawdata = self.args.infile.read(2)
        
KCFile().Process()
