
"""
This Program reads in a raw dump from the Acquisition program

The basic data rate of the raw data is 100Khz
Each sample is 2 bytes (Intel format)
The channel list is:

0 1 2 1 2 3 1 2 1 2

Where:

Channel 0 - Track 1 - Read Only audio (reference)  - 10Khz
Channel 1 - Track 2 - Read Only data               - 40Khz
Channel 2 - Track 3 - Read/Write data              - 40Khz
Channel 3 - Track 4 - Read/Write audio (reference) - 10Khz

This program does several things:
    - Seperates the channel data into seperate files
    - Scales the data appropriately (12 bit unsigned to 16 bit signed)
        0 becomes -32768
        2048 becomes 0
        4095 becomes 32767
    - Uses Linear Interpolation to try to fixup the uneven sampling of the data tracks

"""

def StringToNum(str):
    N = ord(str[0])+ord(str[1])*256
    if N > 32767:
        N = N - 65536
    return N

def NumToString(N):
    if N < 0:
        N = N + 65536
    H = N/256
    L = N%256
    return chr(L) + chr(H)

def Normalize(str):
    N = StringToNum(str)
    N = (N - 2048)*16
    return NumToString(N)

fp_in = file("test.dat","rb")

fp_out1 = file("test1.pcm","wb")
fp_out2 = file("test2.pcm","wb")
fp_out3 = file("test3.pcm","wb")
fp_out4 = file("test4.pcm","wb")

s = fp_in.read(20)
last2 = 0
last3 = 0
while len(s) == 20:

    # Channel 1
    fp_out1.write(Normalize(s[0:2]))

    # Channel 2
    #  First sample is interpolated
    orig_value2 = StringToNum(Normalize(s[2:4]))
    new_value2 = (5*orig_value2 + last2)/6
    fp_out2.write(NumToString(new_value2))

    #  Second sample is exact
    fp_out2.write(Normalize(s[6:8]))
    last2 = StringToNum(Normalize(s[6:8]))

    #  Third sample is interpolated
    orig_value2 = StringToNum(Normalize(s[12:14]))
    new_value2 = (5*orig_value2 + last2)/6
    fp_out2.write(NumToString(new_value2))

    #  Fourth sample is exact
    fp_out2.write(Normalize(s[16:18]))
    last2 = StringToNum(Normalize(s[16:18]))

    # Channel 3

    #  First sample is interpolated
    orig_value3 = StringToNum(Normalize(s[4:6]))
    new_value3 = (5*orig_value3 + last3)/6
    fp_out3.write(NumToString(new_value3))

    #  Second sample is exact
    fp_out3.write(Normalize(s[8:10]))
    last3 = StringToNum(Normalize(s[8:10]))

    #  Third sample is interpolated
    orig_value3 = StringToNum(Normalize(s[14:16]))
    new_value3 = (5*orig_value3 + last3)/6
    fp_out3.write(NumToString(new_value3))

    #  Fourth sample is exact
    fp_out3.write(Normalize(s[18:20]))
    last3 = StringToNum(Normalize(s[18:20]))

    # Channel 4
    fp_out4.write(Normalize(s[10:12]))

    s = fp_in.read(20)

fp_in.close()
fp_out1.close()
fp_out2.close()
fp_out3.close()
fp_out4.close()
