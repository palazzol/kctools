# -*- coding: utf-8 -*-
"""
Created on Sat Nov 12 15:37:01 2016

@author: palazzol
"""

# Tape image decode script

import argparse
import wave
import sys
import math

class PerBit:
    def __init__(self,args):
        self.args = args
        self.state = 'wzeros'
        
    def ProcessBit(self,ifrac,bit):                 
        self.args.outfile.write(bit)

class PerTransition:
    
    def __init__(self,args,samples_per_bit,framerate):
        self.args = args
        self.nominal_samples_per_bit = samples_per_bit
        self.absolute_percent_threshold = 75.0
        self.relative_percent_threshold = 10.0
        self.energy_threshold = 500.0
        self.framerate = framerate
        self.perbit = PerBit(args)
        # State Variables
        self.last_ifrac = None
        self.expecting_short = False
        self.working_samples_per_bit = samples_per_bit
        self.SetTimeThresholds()
        self.num_deltas = 0
        self.total_deltas = 0.0
        
    def AddDelta(self,delta):
        self.num_deltas = self.num_deltas + 1
        self.total_deltas = self.total_deltas + delta
        

    def SetTimeThresholds(self):
        self.short_bottom = (2.0-self.absolute_percent_threshold/100.0)*self.nominal_samples_per_bit/4.0
        self.short_top =    (2.0+self.absolute_percent_threshold/100.0)*self.nominal_samples_per_bit/4.0
        self.long_bottom =  (4.0-self.absolute_percent_threshold/100.0)*self.nominal_samples_per_bit/4.0
        self.long_top     = (4.0+self.absolute_percent_threshold/100.0)*self.nominal_samples_per_bit/4.0
        
    def Process(self,energy,ifrac):
        "Called for every Transition or every low energy sample"
        ##print(energy,ifrac)
        if energy >= self.energy_threshold:
            # Got Valid Energy Level Threshold
            if self.last_ifrac == None:
                # First Transition
                if self.args.measure:
                    if self.num_deltas != 0:
                        print(self.total_deltas/self.num_deltas)
                    self.num_deltas = 0
                    self.total_deltas = 0.0
                self.last_ifrac = ifrac
                #print()
                self.args.outfile.write('time '+str(ifrac/self.framerate)+'\n')
                self.args.outfile.write('data ')
            else:
                # At least 2 transitions with valid energy
                delta = ifrac - self.last_ifrac
                self.last_ifrac = ifrac
                
                #print(delta, ifrac)
                if delta > self.long_top:
                    interval = 'w'
                elif delta >= self.long_bottom:
                    interval = 'L'
                elif delta > self.short_top:
                    interval = 'm'
                elif delta >= self.short_bottom:
                    interval = 'S'
                else:
                    interval = 's'
                    
                if self.expecting_short:
                    if not self.args.measure:
                        if interval == 'S':
                            self.perbit.ProcessBit(ifrac,'1')
                        else:
                            self.perbit.ProcessBit(ifrac,interval)
                    self.expecting_short = False
                else:
                    if interval == 'L':
                        if self.args.measure:
                            self.AddDelta(delta)
                        else:
                            self.perbit.ProcessBit(ifrac,'0')
                        #self.nominal_samples_per_bit = delta
                        #self.SetTimeThresholds()
                    elif interval == 'S':
                        self.expecting_short = True
                    else:
                        if not self.args.measure:
                            self.perbit.ProcessBit(ifrac,interval)
        else:
            if self.last_ifrac != None:
                self.perbit.ProcessBit(ifrac,'e')
                self.args.outfile.write('\ntime '+str(ifrac/self.framerate)+'\n')
            self.last_ifrac = None
            self.expecting_short = False
    
class PerSample:
    def __init__(self, args, framerate):
        self.framerate = framerate
        self.samples_per_bit = framerate / args.bitrate
        # NRZI should go to max/min over 2 bit periods, picked 10 to smooth things
        self.energy_window = math.ceil(self.samples_per_bit*10)
        self.sample_buffer = []
        #self.last_ifrac = 0.0
        self.pertransition = PerTransition(args,self.samples_per_bit,self.framerate)

    def Process(self,i,sample):
        "Called for Every Sample to be processed"
        self.sample_buffer.append(sample)
        if len(self.sample_buffer) > self.energy_window:
            self.sample_buffer.pop(0)
        if len(self.sample_buffer) == self.energy_window:
            # define energy as max-min over the window
            energy = max(self.sample_buffer) - min(self.sample_buffer)
            # define decision threshold as (max+min)/2 over the window
            #threshold = (max(self.sample_buffer) + min(self.sample_buffer)) / 2.0
            threshold = 0.0
            prev_sample = self.sample_buffer[self.energy_window-2]
            # did we get a transition?
            if math.copysign(1,prev_sample-threshold) != math.copysign(1,sample-threshold):
                # calculate interpolated sample
                span = math.fabs(sample-prev_sample)
                frac = math.fabs(prev_sample-threshold)
                ifrac = (i-1) + frac/span
                ##print(threshold)
                #print(prev_sample,sample,threshold,i-1,i,ifrac)
                #print(ifrac - last_ifrac)
                ##print(energy,ifrac)
                self.pertransition.Process(energy,ifrac)
                ###process_transition(energy,ifrac)
                #last_ifrac = ifrac
    
class KCFile:
    def __init__(self):
        parser = argparse.ArgumentParser(description='Decode KC tape data.')
        parser.add_argument('infile', type=argparse.FileType('rb'), help='Input file to decode')
        parser.add_argument('-o','--outfile', type=argparse.FileType('w'), default=sys.stdout, help='Output file')
        parser.add_argument('-t','--track', type=int, default=0, help='track number (default=0)')
        parser.add_argument('-b','--bitrate', type=float, default=3000.0, help='nominal bitrate (default=3000.0)')
        parser.add_argument('-e','--energy', type=float, default=3.0, help='energy window (default=3.0 bits)')
        parser.add_argument('-m','--measure', action='store_true', help='measure mode')
        self.args = parser.parse_args()
        self.numtracks = None
        self.framerate = None
        self.sampwidth = None
        self.nframes = None
        self.persample = None
        self.args.outfile.write('cmds')
        for arg in sys.argv:
            self.args.outfile.write(' '+arg)
        self.args.outfile.write('\n')
        self.args.outfile.write('args '+str(self.args)+'\n')
        
    def Process(self):
        wr = wave.Wave_read(self.args.infile)
    
        self.numtracks = wr.getnchannels()
        self.framerate = wr.getframerate()
        self.sampwidth = wr.getsampwidth()
        self.nframes = wr.getnframes()

        if self.args.track >= self.numtracks:
            print('Error, file only has '+str(self.numtracks)+' tracks.')
            sys.exit(-1)
    
        self.persample = PerSample(self.args, self.framerate)
        
        offset = self.args.track*self.sampwidth
            
        for i in range(0,self.nframes):
            frame = wr.readframes(1)
            # Get one signed, 16-bit sample
            sample = frame[offset]+frame[offset+1]*256
            if sample > 32767:
                sample = sample - 65536
            self.persample.Process(i,sample)
        
KCFile().Process()

    
    
