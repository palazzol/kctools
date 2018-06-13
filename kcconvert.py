# -*- coding: utf-8 -*-
"""
Created on Tue Dec  6 22:01:27 2016

@author: palazzol
"""

# Tape image convert script

import argparse
import sys

class PerLine:
    def __init__(self, args):
        self.args = args
        self.fpout = 0
        self.CreateECCTable()
        self.record = 1

    def CreateECCTable(self):
        low_syndrome = [0x00,0x0d,0x1a,0x17,0x15,0x18,0x0f,0x02,
                0x0b,0x06,0x11,0x1c,0x1e,0x13,0x04,0x09,
                0x16,0x1b,0x0c,0x01,0x03,0x0e,0x19,0x14,
                0x1d,0x10,0x07,0x0a,0x08,0x05,0x12,0x1f]

        high_syndrome = [0x00,0x13,0x07,0x14,0x0e,0x1d,0x09,0x1a,
                0x1c,0x0f,0x1b,0x08,0x12,0x01,0x15,0x06,
                0x19,0x0a,0x1e,0x0d,0x17,0x04,0x10,0x03,
                0x05,0x16,0x02,0x11,0x0b,0x18,0x0c,0x1f]

        """
        low_mask = [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x40,
                0x00,0x00,0x00,0x08,0x00,0x01,0x08,0x00,
                0x00,0x00,0x00,0x20,0x00,0x04,0x10,0x00,
                0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00]

        num_errors = [0x00,0x01,0x01,0x02,0x01,0x02,0x02,0x01,
                0x01,0x02,0x02,0x01,0x02,0x01,0x01,0x02,
                0x01,0x02,0x02,0x01,0x02,0x01,0x01,0x02,
                0x02,0x01,0x01,0x02,0x01,0x02,0x02,0x02]
        """
                
        # map from bad code, to tuple (status, fixed_code)
        self.ecc = {}
        # first, add correct codes
        for i in range(0,1024):
            code = i | (high_syndrome[(i>>5)&0x1f] ^ low_syndrome[i&0x1f]) << 10
            self.ecc[code] = (1,code)
        # now add single-bit errors
        correct_keys = list(self.ecc.keys())
        for k in correct_keys:
            for bad_bit in range(0,15):
                bad_code = k ^ (1<<bad_bit)
                self.ecc[bad_code] = (2,k)
        for i in range(0,32768):
            if self.ecc.get(i) == None:
                self.ecc[i] = (0,0)
                
    def DecodeChunk(self, row_array):
        column_array = [0] * 32
        i = 0        
        for row in row_array:
            for j in range(0,32):
                column_array[j] = column_array[j]*2 + ((row >> (31-j))&1)
            i = i + 1
        for i in range(0,32):
            #print(column_array[i])
            t = self.ecc[column_array[i]]
            #print(column_array[i],t)
            if t[0] == 2:
                #print("Fixed Bit",column_array[i],'->',t[1])
                column_array[i] = t[1]
            if t[0] == 0:
                print("Error!!")
                sys.exit()
        return column_array
        
    def Process(self,line):
        #print(len(line))
        c_count = 0
        state = 0
        zero_count = 0
        counting_zeros = True
        sync_pattern = ''
        char_count = 0
        row_count = 0
        chunk_count = 0
        for c in line:
            if state == 0:
                if c == '0':
                    if counting_zeros:
                        zero_count = zero_count + 1
                        #print('0',end='')
                else:
                    counting_zeros = False
                sync_pattern = sync_pattern + c
                if len(sync_pattern) > 32*4:
                    sync_pattern = sync_pattern[1:]
                if sync_pattern == "00000000000000000000000001111110000000000000000000000000101111010000000000000000000000001101101100000000000000000000000011100111":
                    #print("\nZero Count =",zero_count-25)
                    #print(sync_pattern[25:],end='')
                    self.args.outfile.write('zero '+str(zero_count-25)+'\n')                    
                    state = 1
                    row = 0
                    char_count = 0
                    row_count = 0
                    chunk_count = 0
                    row_array = []
            elif state == 1:
                row = row * 2
                if c == '1':
                    row = row + 1
                char_count = char_count + 1
                if char_count == 37:
                    if (row & 0x1f00000000) == 0x1d00000000:
                        row_array.append(row & 0xffffffff)
                    else:
                        print("\nError!",c_count)
                        sys.exit()
                    row = 0
                    char_count = 0
                    row_count = row_count + 1
                if row_count == 15:
                    column_array = self.DecodeChunk(row_array)
                    """
                    for i in range(0,15):
                        print('11101',end='')
                        for j in range(0,32):
                            if (column_array[j] >> (14-i)) & 0x01:
                                print('1',end='')
                            else:
                                print('0',end='')
                    """
                    if self.fpout == 0:
                        #self.fpout = open('record'+str(column_array[0]&0x3ff)+'.bin','wb')
                        self.fpout = open('record_'+str(self.record)+'.bin','wb')
                        self.args.outfile.write('file record_'+str(self.record)+'.bin\n')
                        self.record = self.record + 1
                    for j in range(0,32):
                        val = column_array[j]&0x3ff
                        self.fpout.write(bytearray([val>>8,val&0xff]))
                    row_array = []
                    chunk_count = chunk_count + 1
                    #print(ca[0]&0x3ff,end=' ')
                    row_count = 0
            #print('c_count:',c_count)
            c_count = c_count + 1
        if state==0 and zero_count > 0:
            self.args.outfile.write('zero '+str(zero_count)+'\n')
        #print()
        if self.fpout != 0:
            self.fpout.close()
            self.fpout = 0
        #print('chunk_count=',chunk_count,'  row_count=',row_count,'  char_count=',char_count)
                    
                
                    
                
    
class KCFile:
    def __init__(self):
        parser = argparse.ArgumentParser(description='Verify KC tape data.')
        parser.add_argument('infile', type=argparse.FileType('r'), help='Input file to verify')
        parser.add_argument('-o','--outfile', type=argparse.FileType('w'), default=sys.stdout, help='Output file')
        self.args = parser.parse_args()
        self.numtracks = None
        self.framerate = None
        self.sampwidth = None
        self.nframes = None
        self.persample = None
        
    def Process(self):
        self.perline = PerLine(self.args)
        count = 1
        for line in self.args.infile:
            if line[0:len('cmds')] == 'cmds':
                self.args.outfile.write(line)
            elif line[0:len('args')] == 'args':
                self.args.outfile.write(line)
            elif line[0:len('time')] == 'time':
                self.args.outfile.write(line)
            elif line[0:len('data ')] == 'data ':
                self.perline.Process(line[5:])
        
KCFile().Process()

    
    
