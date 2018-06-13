# -*- coding: utf-8 -*-
"""
Created on Tue Dec  6 22:26:17 2016

@author: palazzol
"""

num = 'a'

def read10():
    global fp
    global num
    loc = fp.tell()
    if loc == 0x1080:
        fp.close()
        num = chr(ord(num) + 1)
        fp = open('record'+num+'.bin','rb')
        fp.seek(0x80)
    b = fp.read(2)
    return int(b[0])*256+int(b[1]) & 0xff

def read16():
    low = read10()
    high = read10()
    return high*256+low
    
# detokenizer

tokens = ['END','FOR','NEXT','DATA','INPUT','DIM','READ','LET','GOTO',
          'RUN','IF','RESTORE','GOSUB','RETURN','REM','STOP','ON','PLOD','PSAV',
          'VLOD','VSAV','DEF','SLOD','PRINT','CONT','LIST','CLEAR','PRT',
          'NEW','TAB(','TO','FN','SPC(','THEN','NOT','STEP','+','-','*','/',
          '#','AND','OR','>','=','<','SGN','INT','ABS','VER','FRE','POS',
          'SQR','RND','LOG','EXP','COS','SIN','TAN','ATN','GETC','LEN',
          'STR$','VAL','ASC','CHR$','LEFT$','RIGHT$','MID$','GO']


fp = open('record'+num+'.bin','rb')
fp.seek(0x80)
offset = read16()
while offset != 0x0000:
    line = read16()
    print(line,end=' ')
    b = read10()
    while b != 0:
        if b>127:
            print(tokens[b-128],end='')
        else:
            print(chr(b),end='')
        b = read10()
    print()
    offset = read16()
fp.close()




