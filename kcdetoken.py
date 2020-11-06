# -*- coding: utf-8 -*-
"""
Created on Tue Dec  6 22:26:17 2016

@author: palazzol
"""

import sys

# detokenizer

class Detokenizer:
    def __init__(self, num):
        self.tokens = ['END','FOR','NEXT','DATA','INPUT','DIM','READ','LET','GOTO',
              'RUN','IF','RESTORE','GOSUB','RETURN','REM','STOP','ON','PLOD','PSAV',
              'VLOD','VSAV','DEF','SLOD','PRINT','CONT','LIST','CLEAR','PRT',
              'NEW','TAB(','TO','FN','SPC(','THEN','NOT','STEP','+','-','*','/',
              '#','AND','OR','>','=','<','SGN','INT','ABS','VER','FRE','POS',
              'SQR','RND','LOG','EXP','COS','SIN','TAN','ATN','GETC','LEN',
              'STR$','VAL','ASC','CHR$','LEFT$','RIGHT$','MID$','GO']
        self.num = int(num)
        
    def Run(self):
        numString = "%04d" % self.num
        self.fp = open('record_'+numString+'.bin','rb')
        self.fp.seek(0x80)
        offset = read16()
        while offset != 0x0000:
            line = read16()
            print(line,end=' ')
            b = read10()
            startOfLine = 1
            while b != 0:
                if b>127:
                    if startOfLine != 1:
                        print(' ',end='')
                    print(tokens[b-128],end=' ')
                else:
                    print(chr(b),end='')
                b = read10()
                startOfLine = 0
            print()
            offset = read16()
        self.fp.close()

    def read10(self):
        loc = self.fp.tell()
        if loc == 0x1080:
            self.fp.close()
            self.num = self.num + 1
            numString = "%04d" % self.num
            self.fp = open('record_'+numString+'.bin','rb')
            self.fp.seek(0x80)
        b = self.fp.read(2)
        # Note that in spite of the code below, only the lower 8-bits are returned since Python
        # defines that & operator has low precedence than + or *, so the & 0xff executes last
        # and masks off the top bits.  However, if this was fixed, then kcdetoken.py would fail
        # since *.bin files often have long stretches where the top byte is 0x03 instead of 0x00.
        return int(b[0])*256+int(b[1]) & 0xff
    
    def read16(self):
        low = read10()
        high = read10()
        return high*256+low
    
####################

if len(sys.argv) != 2:
    print('Usage: '+sys.argv[0]+' <recordnum>')
    sys.exit(-1)
    
d = Detokenizer(sys.argv[1])
d.Run()

