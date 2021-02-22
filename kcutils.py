# -*- coding: utf-8 -*-
"""
Created on Wed Dec 30 2020

@author: Chris Dreher
"""

from array import *
import os.path
import argparse
import sys
import re



class KCStatusPrinter:
    """
    Class for printing of status
    Note: might be expanded for advanced logging, but for now is a simple implementation.
    """

    def __init__(self, doPrintStatus ):
        """
        Initializer
            doPrintStatus       - boolean for whether to print when opening a new record file
        """
        self.doPrintStatus = doPrintStatus
    
    def printStatus(self, indentLevel, text ):
        """
        Simple status printer
            indentLevel   - Integer >= 0 of how many levels to indent by.  Each level indents multiple spaces
            text          - String to print
        """
        if self.doPrintStatus:
            print( text.rjust( len(text) + 4 * indentLevel ) )
            
    def errorPrint( self, exitMessage ):
        """
        Prints an error message
        """
        print( 'ERROR: ' + exitMessage )
            
    def errorExit( self, exitNumber, exitMessage ):
        """
        Prints an error message and exits the whole program
        """
        self.errorPrint( exitMessage )
        sys.exit( exitNumber )



class MCMemoryMap:
    """
    Represents the memory map, as seen by the Master Component.
    Note: Only the 64K memory map is supported.  Thus, bank-switching is not supported.
    """

    SIZE           = 65536
    STATE_EMPTY    = 0
    STATE_WRITTEN  = 1

    def __init__(self, canOverwrite, statusPrinter):
        """
        Initializer.
            canOverwrite    - a boolean for whether prior data can be overwritten by poke()
            statusPrinter   - KCStatusPrinter for printing
        """
        self._canOverwrite  = not ( canOverwrite == False or canOverwrite == None )
        self._printer       = statusPrinter
        # Initialize the 2 arrays
        self._data          = array('H')
        self._state         = array('B')
        self._data.append(0)
        self._data          *= self.SIZE
        self._state.append(self.STATE_EMPTY)
        self._state         *= self.SIZE

    def readWord( self, address ):
        """
        Returns the value stored at the address.  Returns a default value if not yet written to.
        """
        return self._data[address]

    def readLowByte( self, address ):
        """
        Returns the value stored at the address.  Returns a default value if not yet written to.
        """
        return self._data[address] & 0xff
        
    def readLowBytesAsWord( self, address ):
        """
        Reads a word from 2 sequential addresses in little-endian order.
        """
        return ( self.readLowByte( address + 1 ) << 8 ) | self.readLowByte( address )

    def writeWord( self, address, dataWord, forceOverwrite=False ):
        """
        Writes the data value to the specified address, if it is legal to do so.
        """
        # print( "    $%04x = $%04x" % (address, dataWord) )  # Noisy debug printing
        if self._canOverwrite == True or forceOverwrite == True or \
           self._state[address] == self.STATE_EMPTY or self._data[address] == dataWord:
            self._data[address]  = dataWord
            self._state[address] = self.STATE_WRITTEN
        else:
            self._printer.errorExit( 1, 'Attempted to overwrite address $%04x that contains data of $%04x with the data $%04x' % \
                                        ( address, self._data[address], dataWord ) )

    def writeLowBytesAsWord( self, address, dataWord, forceOverwrite=False ):
        """
        Writes the data word to 2 sequential addresses in little-endian order.
        """
        self.writeWord( address    , dataWord & 0xff, forceOverwrite )
        self.writeWord( address + 1, ( dataWord >> 8 ) & 0xff, forceOverwrite )
        
    def writeByteBuffer( self, address, bufferData, bufferStart, bufferLenInBytes, originalText, forceOverwrite=False ):
        """
        Writes the data value to the specified address, if it is legal to do so.
        """
        if bufferStart < 0 or bufferLenInBytes < 1:
            self._printer.errorExit( 2, 'The buffer start index or the len of the buffer portion to copy is negative.  Original text: %s' \
                                         % originalText )
        bufferEnd = bufferStart + bufferLenInBytes
        if bufferEnd > len( bufferData ):
            self._printer.errorExit( 2, 'The buffer end index is larger than the BIN file\'s length.  Original text: %s' % originalText )
        for i in range( bufferStart, bufferEnd, 2 ):
            self.writeWord( address + ( ( i - bufferStart ) >> 1 ), ( ( bufferData[i] & 0xff) << 8 ) | ( bufferData[i+1] & 0xff), forceOverwrite )

    def getWordState( self, address ):
        """
        Returns the state (ex: STATE_EMPTY, STATE_WRITTEN) for the specified address
        """
        return self._state[address]
        
    def checkStateRange( self, address, lengthInWords, state, mustMatch ):
        """
        Returns boolean whether every word in the address range is in the expected state.  Can check negative states.
            address         - Integer address
            lengthInWords   - Integer number of words to check
            state           - The state to check, must be one of the STATE_ values.  See mustMatch for how checking is done
            mustMatch       - Boolean that controls what kind of check is done:
                              True means that the state of all the addresses must BE the same at the state passed in.
                              False means that the state of all the addresses must NOT BE the same at the state passed in.
        """
        for i in range( address, address + lengthInWords ):
            if ( self._state[i] == state ) != mustMatch:
                return False
        return True
        
    def alignMemoryBlock( self, blockSize ):
        """
        Align later output memory blocks to the specified blockSize.  blockSize is the number of bits (1-16).
        Blocks are aligned to blockSize boundaries.
        """
        if blockSize <= 1:
            return
        mask        = ( self.SIZE - 1 ) & ~( ( 1 << blockSize ) - 1 )
        foundWrite  = False
        for address in range( 0, self.SIZE ):
            if address == ( address & mask ):
                foundWrite = False
            if foundWrite == False and self._state[address] == self.STATE_WRITTEN:
                # Update the previous addresses
                for settingAddress in range( address & mask, address ):
                    self._state[settingAddress] = self.STATE_WRITTEN
                foundWrite = True
            if foundWrite == True:
                self._state[address] = self.STATE_WRITTEN
        debugPrintState()
               
    def debugPrintState(self):
        """
        Logs the entire memory map's state.
        """
        logLine = None
        for address in range( 0, self.SIZE ):
            if address % 64 == 0:
                logLine = '$%04x : ' % address
            logLine += '%d' % self._state[address]
            if address % 64 == 63:
                self._printer.printStatus( 1, logLine )
                logLine = None



class MemoryStreamReader:
    """
    Class that treats a memory block as a stream of bytes/decles/words
    """
    def __init__(self, memoryMap, startAddress, length, statusPrinter ):
        self.memoryMap      = memoryMap
        self.startAddress   = startAddress
        self.length         = length
        self.index          = 0
        self.statusPrinter  = statusPrinter
        
    def read10(self):
        """
        Returns a decle from memory, advances the read head.
        """
        if self.index >= self.length:
            self.statusPrinter.errorExit( 1, "Read off the end of the memory block" )
        value = self.memoryMap.readWord( self.startAddress + self.index )
        self.index += 1
        return value

    def read8(self):
        """
        Returns the lower byte from a memory location, advances the read head.
        """
        return self.read10() & 0xff

    def read16(self):
        """
        Returns a word from memory by reading 2 bytes, advances the read head.
        """
        low  = self.read8()
        high = self.read8()
        return ( high << 8 ) | low

    def read16BE(self):
        """
        Returns a word from memory by reading 2 bytes in BIG-endian format, advances the read head.
        """
        high = self.read8()
        low  = self.read8()
        return ( high << 8 ) | low

    def getRemainingLength(self):
        """
        Returns the number of readable decles.
        """
        if self.index >= self.length:
            return 0
        return self.length - self.index
        
    def setIndex(self, newIndex):
        """
        Sets the index to a new value (ex: after backing up to re-read some memory)
        """
        self.index = newIndex



class KCBasicUtils:
    """
    A 'static' class that parses portions of KC BASIC memory structures.
    """

    # A lot of the below code is one-time initialization of look-up tables and such.

    # String are composed of 1-byte characters or 3-byte characters.  Some are displayable while others
    # cause the system to take an action (such delete a character, clear the screen, or set a flag).
    #
    # Undocumented 1-byte control characters (lone chr$(x)):
    #   0, 3, 5, 16, 17, 19, 31     Nothing observable
    #   14                          Garbage char overwrites character to the left of cursor
    #   15                          Garbage char overwrites character to the left of cursor
    #   18                          Garbage char overwrites at cursor, moves cursor to right
    #   20                          Moves cursor to the right
    #   30                          Grave accent, i.e. the ` character  (not 31 as is documented)
    #
    # Ranges for chr$(27)+chr$(Y)+chr$(64+X)
    #   Y   X range     Desciption
    #   -   -------     ----------
    #   16  1 - 64      Special chars instead of control characters (upper half is ASCII symbols and numbers)
    #   17  1 - 64      ASCII upper and lower case, some symbols, cents instead of del
    #   18  1 - 64      Blocky squares
    #   19  1 - 64      Braille
    #   20  1 - 39      Horizontal cursor position
    #   21  1 - 24      Vertical cursor position
    #   22  0 - 38      Left margin
    #   23  1 - 39      Right margin
    #   24  1 - 24      Top margin
    #   25  1 - 24      Bottom margin
    #   26  1 - 64      Cursor blink rate.  1 = fastest, 62 = slowest, 63 = solid on, 64 = solid off
    #   27  0 - 63      REPEAT key speed.  0 = fastest, 63 = slowest.  Default is 2.
    #   28  1 - 36      Hardcoded strings in LOWER case.    Strings are in KC EXEC.  They are located at
    #   29  1 - 36      Hardcoded strings in PASCAL case.   $CC4A - $CDF7.  Their lengths are at $CC17 - $CC49.
    #   30  1 - 36      Hardcoded strings in UPPER case.    
    #   31  various     Misc flags.  They are paired by values that differ by 16.  Most bits are similar to
    #                   GETC's flags parameter except here bit 5 indicates upper vs lower nibble.
    #                       OFF ON  Desciption              Default
    #                       --- --  ----------              -------
    #                        1  17  Typing echo             ON
    #                        2  18  Force Upper Case        OFF
    #                        4  20  GETC Wait For EOL       OFF
    #                        8  24  Keystroke Dings         ON
    #                       33  49  Auto LF after CR        ON
    #                       34  50  No Screen Scrolling     OFF
    #                       36  52  Overflow To Next Line   ON
    #                       40  56  Hide Chars and Cursor   OFF
    #
    # Characters 0-31 (00-1F) in chr$(27)+chr$(16)+chr$(64+X):
    #                       KC Char Desciption                  Unicode
    #       Dec Hex  ASCII  chr$(27)chr$(16)..  Console Font    Codepoint
    #       --- ---  -----  ------------------  ------------    ---------
    #        0  00   nul    Down Arrow          2193            2193
    #        1  01   soh    Inverted !          00A1            00A1
    #        2  02   stx    Inverted "          201E            201E
    #        3  03   etx    Up-Left corner      250C            250C
    #        4  04   eot    Horizontal edge     2500            2500
    #        5  05   enq    Up-Right corner     2510            2510
    #        6  06   ack    Btm-Left corner     2514            2514
    #        7  07   bel    Btm-Right corner    2518            2518
    #        8  08    bs    Intersect no-up     252C            252C
    #        9  09   tab    Intersect no-down   2534            2534
    #       10  0A    lf    Intersect no-left   251C            251C
    #       11  0B    vt    Intersect no-right  2524            2524
    #       12  0C    ff    Intersect all       253C            253C
    #       13  0D    cr    C with cedilla      00E7            00E7
    #       14  0E    so    n with tilde        00F1            00F1
    #       15  0F    si    Inverted ?          00BF            00BF    
    #       16  10   dle    a w/ diaeresis      00E4            00E4
    #       17  11   dc1    a w/ circumflex     00E2            00E2
    #       18  12   dc2    a w/ grave          00E0            00E0
    #       19  13   dc3    a w/ acute          00E1            00E1
    #       20  14   dc4    e w/ circumflex     00EA            00EA
    #       21  15   nak    e w/ grave          00E8            00E8
    #       22  16   syn    e w/ acute          00E9            00E9
    #       23  17   etb    i w/ circumflex     00EE            00EE
    #       24  18   can    i w/ acute          00ED            00ED
    #       25  19    em    o w/ diaeresis      00F6            00F6
    #       26  1A   sub    o w/ circumflex     00F4            00F4
    #       27  1B   ecs    o w/ acute          00F3            00F3
    #       28  1C    fs    u w/ diaeresis      00FC            00FC
    #       29  1D    gs    u w/ circumflex     00FB            00FB
    #       30  1E    rs    u w/ grave          00F9            00F9
    #       31  1F    us    u w/ acute          00FA            00FA
    # Printable ASCII characters that the KC deviates from:
    #       94  5E    ^     Up Arrow            2192            2192
    #       96  60    `     Cents               00A2            00A2
    # Delete character:
    #      IMPORTANT: the below is true ONLY for chr$(27)+chr$(17)+chr$(127)
    #      127  7F   del    Cents               00A2            00A2
    # Squares:
    #      128      80      <blank>             0020            0020
    #      129-148  81-94   patterned squares   ----            1FB00-1FB13
    #      149      95      left vertical half  258C            258C
    #      150-169  96-A9   patterned squares   ----            1FB14-1FB27
    #      170      AA      right vertical half 2590            2590
    #      171-190  AB-BE   patterned squares   ----            1FB28-1FB3B
    #      191      BF      solid square        2588            2588
    # Braille:
    #      Note: The KC dots are in horizontal order while Unicode are in vertical order
    #      Thus, the KC bit indices of 543210 are re-ordered to 531420 to match Unicode's ordering.
    #      192-255  C0-FF   Braille dots        ----            2800-283F
    #
    # Few fonts support the Unicode range 1FB00-1FB3D ("Symbols for Legacy Computing") and 2800-283F (braille).
    # Some fonts that do are:
    #   Fairfax HD                      Fixed Width     Free (SIL Open Font License)
    #   PragmataPro Liga Regular        Fixed Width     Paid Commercial ($$$)
    #   BabelStone Shapes               Proportional    Free (SIL Open Font License)
    #
    
    # KC's control characters.  All strings below are ASCII printable so 'format' checks are unnecessary.
    # Note: 127 a control character but ONLY as 1 byte sequence
    controlCharsDict = {     1:'^SCROLL_UP_CURSOR_DOWN^',       \
                             2:'^SCROLL_DOWN_CURSOR_UP^',       \
                             4:'^DELETE_TO_EOL^',               \
                             6:'^CURSOR_TO_EOL^',               \
                             7:'^BELL^',                        \
                             8:'^BACKSPACE^',                   \
                             9:'^TAB^',                         \
                            10:'^LINEFEED^',                    \
                            11:'^CURSOR_TO_UPPER_LEFT^',        \
                            12:'^CLEAR_SCREEN^',                \
                            13:'^CARRIAGE_RETURN^',             \
                            21:'^DELETE_TO_BOL^',               \
                            22:'^INSERT_SPACE^',                \
                            23:'^INSERT_LINE^',                 \
                            24:'^DELETE_CURRENT_CHAR^',         \
                            25:'^DELETE_TO_EOL_APPEND_NEXT^',   \
                            26:'^CLEAR_INSIDE_MARGINS^',        \
                            27:'^ESCAPE^',                      \
                            28:'^CURSOR_UP^',                   \
                            29:'^CURSOR_RIGHT^',                \
                            30:'`',                             \
                           127:'^DELETE_PREVIOUS^' }
                            # Note: the ` is incorrectly documented as 31.  It is the
                            # only displayable character in the control character range.

    # KC's displayable characters, separated by output formats
    # Note: 127 is KC displayable but ONLY as a 3-byte escape sequence
    formatDicts = {}
    
    # acsii format
    formatDicts['ascii'] = dict( zip( range( 0x20, 0x7F ), range( 0x20, 0x7F ) ) )
    del formatDicts['ascii'][0x5E]   # the UP_ARROW KC character is not ASCII
    del formatDicts['ascii'][0x60]   # the CENTS KC character is not ASCII
    # ansi format.
    formatDicts['ansi'] = dict( list( formatDicts['ascii'].items() ) +              \
                                list( {  1:0x00A1, 13:0x00E7, 14:0x00F1, 15:0x00BF, \
                                        16:0x00E4, 17:0x00E2, 18:0x00E0, 19:0x00E1, \
                                        20:0x00EA, 21:0x00E8, 22:0x00E9, 23:0x00EE, \
                                        24:0x00ED, 25:0x00F6, 26:0x00F4, 27:0x00F3, \
                                        28:0x00FC, 29:0x00FB, 30:0x00F9, 31:0x00FA, \
                                        96:0x00A2,127:0x00A2                        }.items() ) )
    # win-console format
    # Note: Supported Unicode codepoints based on the Consolas, Courier New, and Lucida Console fonts.
    formatDicts['win-console'] =  dict( list( formatDicts['ansi'].items() ) +               \
                                        list( {  0:0x2193,  2:0x201E,  3:0x250C,  4:0x2500, \
                                                 5:0x2510,  6:0x2514,  7:0x2518,  8:0x252C, \
                                                 9:0x2534, 10:0x251C, 11:0x2524, 12:0x253C, \
                                                94:0x2191                                   }.items() ) )
    # braille format
    formatDicts['braille'] =  dict( list( formatDicts['win-console'].items() ) )
    for i in range( 0, 64 ):
        # Mapping KC's braille order to Unicode codepoints is... interesting.
        # KC bit indices of 543210 are re-ordered to 531420.
        value = 0x2800 + ( i & 0x21 | (( i & 0x10 ) >> 2 ) | (( i & 0x04 ) >> 1 ) | \
                                      (( i & 0x08 ) << 1 ) | (( i & 0x02 ) << 2 ) )
        formatDicts['braille'] =  dict( list( formatDicts['braille'].items() ) + \
                                        list( { 192+i:value }.items() ) )
    # unicode format
    formatDicts['unicode'] =  dict( list( formatDicts['braille'].items() ) +    \
                                    list( { 128:0x0020, 149:0x258C, 170:0x2590, 191:0x2588 }.items() ) )
    for i in range(  1, 63 ):
        # Unicode 0x1FBXX range skips a symbol every 21 codepoints, since the skipped codepoints are 
        # already defined elsewhere.  Thus, we have to adjust the offset.
        if i % 21 == 0:
            continue
        offset = 1 + i // 21
        formatDicts['unicode'] =  dict( list( formatDicts['unicode'].items() ) + \
                                        list( { 128+i:0x1FB00+i-offset }.items() ) )

    # A few shorthand constants to ease building the hardcodedStrings
    TB      = controlCharsDict[9]
    LF      = controlCharsDict[10]
    CR      = controlCharsDict[13]
    HPOS    = '^HPOS_CURSOR(%d)^'

    # Hardcoded string table.  
    # In the escape sequence CHR$(27)+CHR$(28+Y)+CHR$(64+X)...
    # The 1st dimension of the list is X
    # The 2nd dimension is the lower-case string and the upper-case string.
    #   index 0     The "lower case" string.  Note that a few strings are not truly all lower case.
    #   index 1     The UPPER case string.  If a string, then that is the value.
    #               If None, then the lower case string is made all upper case.
    hardcodedStrings = [
        [ None,                     None                    ],  # Placeholder, never used.
        [ CR+LF,                    None                    ],
        [ '(Recording)'+CR+LF+TB,   None                    ],
        [ 'rewind',                 None                    ],
        [ CR+LF+' ? ',              None                    ],
        [ 'error',                  None                    ],
        [ 'cartridge',              None                    ],
        [ 'cassette',               None                    ],
        [ 'tape',                   None                    ],
        [ None,                     None                    ],  # Special handling for Intellivision logo
        [ CR+LF+'  > ',             None                    ],
        [ '...',                    None                    ],
        [ 'don\'t',                 None                    ],
        [ 'understand',             None                    ],
        [ 'see',                    None                    ],
        [ 'can\'t',                 None                    ],
        [ 'loading',                'LOADing'               ],
        [ 'sorry',                  None                    ],
        [ 'writer',                 None                    ],
        [ 'start',                  None                    ],
        [ 'resume',                 None                    ],
        [ 'eject',                  None                    ],
        [ 'the',                    None                    ],
        [ 'program',                None                    ],
        [ 'cleaning',               'CLEANing'              ],
        [ 'commands',               'COMMandS'              ],
        [ 'list',                   None                    ],
        [ 'return',                 None                    ],
        [ 'and',                    None                    ],
        [ 'enter',                  None                    ],
        [ 'mode',                   None                    ],
        [ 'head',                   None                    ],
        [ 'type',                   None                    ],
        [ ' one of these ',         ' ONE OF theSE '        ],
        [ 'For index, type "I"',    'FOR INDEX, type "I"'   ],
        [ ', then RETURN',          ', theN RETURN'         ],
        [ 'ing',                    None                    ],
        [ 'K. Smith',               None                    ],  # Undocumented
        [ 'L. Zwick',               None                    ],  # Undocumented
    ]
    
    flagNames = {
         1:'TYPING_ECHO',
         2:'FORCE_UPPER_CASE',
         4:'GETC_WAITS_FOR_EOL',
         8:'KEYSTROKE_DINGS',
        33:'AUTO_LF_AFTER_CR',
        34:'NO_SCREEN_SCROLLING',
        36:'OVERFLOW_TO_NEXT_LINE',
        40:'HIDE_CHARS_AND_CURSOR'
    }

    def generateVarName( memoryStream, statusPrinter ):
        """
        Given a memory stream, read the 2 bytes for a variable's name, and generate the correct string for the variable's name
        Returns object that contains 'name' and 'isString' boolean
        """
        IS_STRING_MASK = 0x80
        
        name1 = memoryStream.read8()
        name2 = memoryStream.read8()

        isString = ( name2 & IS_STRING_MASK ) != 0
        name2 = name2 & ~IS_STRING_MASK
        
        if name1 == 0:
            statusPrinter.errorExit( 1, "Variable's name started with 0x00" )
        name = "%c" % name1
        if not name.isalpha():
            statusPrinter.errorExit( 1, "Variable's 1st name character is an illegal character: %s" % name )

        if name2 != 0:
            name += "%c" % name2
            if not name.isalnum():
                statusPrinter.errorExit( 1, "Variable's name containg illegal characters: %s%s" % 
                                            ( name, "$" if isString else "" ) )

        if isString:
            name = name + "$"
            
        class Result: pass
        result = Result()
        result.name     = name
        result.isString = isString
        return result

    def parseNumber( memoryStream, statusPrinter ):
        """
        Parses a number from the memory stream, returns its value.
        
        Note: when converting the number to a string representation, the printf format of %.08G is recommended.
        This is because there are 24 bits of mantissa, which works out to ~7.225 decimal digits (8th digit is partial)
        This prints all stored digits, even though the KC only displays all these digits.
        Thus, typing the following print statement in KC BASIC results :
            ? 1/3
                .333333
            ? 1/3 - .333333
                3.27826E-07
            ? 1/3 - .3333333
                2.23517E-08     <-- This is 3/8 * 2^-24, which means the bottom 2 bits of the matissa were left over.
            ? 1/3 - .33333333
                0
        """

        # Format for numbers is that they are 4 bytes long with the following format:
        #
        # Exponent Matissa1 Matissa2 Matissa3
        # 76543210 76543210 76543210 76543210     Note
        # -------- -------- -------- --------     ----
        # 00000000 jjjjjjjj jjjjjjjj jjjjjjjj     Value is 0.  j is junk bit, can be leftovers from calculations
        # eeeeeeee Svvvvvvv vvvvvvvv vvvvvvvv     Normal positive integer.  Implied leading 1 for matissa values v (ex: 15 stores 3x 1 bits).
        #                                         S is the sign bit.
        #                                         Exponent is linearly increases from 01 to FF.  80 is the center point, ...
        #                                             ... where the decimal point does not shift either way (80 00 00 00 = 1/2)
        #                                         Decimal point is placed BEFORE the leading one.  Exponent is left-shift amount.

        SIGN_MASK       = 0x800000
        ZERO_EXP_OFFSET = 0x80
        
        exponent = memoryStream.read8() - ZERO_EXP_OFFSET
        mantissa = (memoryStream.read8() << 16) | (memoryStream.read8() << 8) | memoryStream.read8()
        sign     = 1 if ( mantissa & SIGN_MASK ) == 0 else -1
        mantissa = mantissa | SIGN_MASK     # Force the leading 1 to be set
        
        if exponent == -ZERO_EXP_OFFSET:
            return 0
        mantissa *= 1.0     # Make sure the number is floating-point, not 100% sure this is necessary.
        return sign * ( mantissa / SIGN_MASK ) * ( 2 ** ( exponent - 1 ))

    def parseString( memoryStream, hasPadByte, dynamicStringsBlockInfo, programStringOffset, format, statusPrinter ):
        """
        Parses a string from the memory stream, returns KC BASIC representation.  hasPadByte is a boolean.
            memoryStream            - MemoryStreamReader that is expected to be pointing at a string structure
            hasPadByte              - Boolean of whether the string has 1 pad byte at the endian
            dynamicStringsBlockInfo - Result from KCBasicRecordReader.getBlockInfo( ... BLOCK_TYPE_DYNA_STRINGS )
            programStringOffset     - Integer of how much to adjust string addresses that point inside the BASIC program
            format                  - String that indicates the expected format the string will be returned in.
                                      Only 'kcbasic' format is BASIC code compatible (chars inside of "" or escaped with CHR$).
                                      Other formats are for displaying to user, within the limits of the specified character
                                      set.  ^...^ is used for escaping since the KC does not support the ^ character.  User
                                      display formats decode documented and known good escape sequences into characters or
                                      phrases, such as ^BELL^.  Unknown / undocumented / incomplete escape sequences will be
                                      decoded as decimal numbers, such as ^14^.  Consecutive ^ characters will be merged into one
                                      (ex: instead of ^27^^19^^255^, ^27^19^255^ will be returned).
                                        kcbasic     KC BASIC format used by PRINT statements.
                                        ascii       User display format.  Includes support for " and `.
                                        ansi        User display format.  Adds ISO 8859-1 (Unicode < 0x0100)
                                        win-console User display format.  Adds Windows-1252 + IBM CP437 (Unicode 25xx, 201E, 219x)
                                        braille     User display format.  Adds braille Unicode ranges 2800-283F, 2588
                                        unicode     User display format.  Adds Unicode range 1FB00-1FB1D which is the
                                                    "Symbols for Legacy Computing" with 2x3 blocks.  Few fonts support this range.
            statusPrinter           - KCStatusPrinter for logging and errors
        Returns object that contains 'value' (string) and 'isDynamic' (boolean)
        
        Note: Internally, the string pointer address is adjusted to the MC range, not the raw stored KC range.
        """

        # Format for strings in memory is that they are 3 or 4 bytes long with the following format:
        #   byte   Length of string in bytes
        #   word   String's address in little-endian format
        #   byte   Optional padding byte with value 0x00

        length  = memoryStream.read8()
        address = memoryStream.read16() + KCBasicRecordReader.KC_TO_MC_OFFSET
        if hasPadByte:
            padByte = memoryStream.read8()
            if padByte != 0x00:
                statusPrinter.errorExit( 1, "String's pad byte was $02x instead of $00" % padByte )
        if address < KCBasicRecordReader.ADDRESS_START or address > KCBasicRecordReader.ADDRESS_END:
            statusPrinter.errorExit( 1, "String's address of $%04x is out-of-range" % address )

        memoryMap = memoryStream.memoryMap
        if memoryMap.checkStateRange( address, length, MCMemoryMap.STATE_WRITTEN, True ) == False:
            return "Unreadable string of length %d at address $%04x" % ( length, address )

        # Determine if the string is Program or Dynamic.  If program, then adjust the address location by an offset.
        class Result: pass
        result = Result()
        result.value     = ""
        result.isDynamic = False
        dynaAddress = None
        dynaLength  = 0
        if dynamicStringsBlockInfo != None and \
           dynamicStringsBlockInfo.address != 0x0000 and \
           dynamicStringsBlockInfo.length != 0:
            dynaAddress = dynamicStringsBlockInfo.address
            dynaLength  = dynamicStringsBlockInfo.length
        if dynaAddress != None and address >= dynaAddress and address + length <= dynaAddress + dynaLength:
            result.isDynamic = True
        else:
            address += programStringOffset

        if format == 'kcbasic':
            # KC BASIC program format
            hasStartQuote = False
            for i in range( address, address + length ):
                character = memoryMap.readLowByte( i )
                if character >= 0x20 and character <= 0x7E and character != 0x22 and character != 0x5E and character != 0x60:
                    # Can't directly print the " character, the ↑ character, or the ¢ character (respectively)
                    if hasStartQuote == False:
                        if len( result.value ) > 0:
                            result.value += '+'
                        result.value += '"'
                        hasStartQuote = True
                    result.value += chr( memoryMap.readLowByte( i ) )
                else:
                    if hasStartQuote == True:
                        result.value += '"'
                        hasStartQuote = False
                    if len( result.value ) > 0:
                        result.value += '+'
                    result.value += 'CHR$(%d)' % character
            if len(result.value) == 0:
                result.value = '""'
            elif hasStartQuote == True:
                result.value += '"'
        else:
            # A user display format
            i = address
            while i < address+length:
                character = memoryMap.readLowByte( i )
                escGroup  = None
                escChar   = None
                if character == 27 and i+2 < address+length:
                    escGroup = memoryMap.readLowByte( i + 1 )
                    escChar  = memoryMap.readLowByte( i + 2 )
                    i += 2

                result.value += KCBasicUtils.parseCharacter( character, escGroup, escChar, format, statusPrinter )
                i += 1
                
            # Get rid of any excessive ^^
            result.value = result.value.replace( '^^', '^' )
        return result

    def buildIntellivisionLogo( format, statusPrinter ):
        """
        Returns the string for the Intellivision logo, based on the given format.
        """
        # Parse the raw logo based off of the format.
        result  = ''
        rawLogo = bytes.fromhex( '00 02 BF 00 08 A0 00 17 96 0A 00 02 BF A8 BD 80' + \
                                 '95 AE BF 84 BE 83 AA 95 80 BF 80 8A 85 BF 90 80' + \
                                 'BA 8A 85 BE 9F 83 81 8F A8 9F AF 94 BE 94 AA 54' + \
                                 '4D 0A 00 02 BF AA 8B BD 95 AA BF 80 BF 83 AA 95' + \
                                 '80 BF 80 AA 95 AB B5 A8 95 AA 95 8B AF BD 90 BF' + \
                                 'AA 80 80 95 97 AF BE 0A 00 02 BF AA 80 AB 95 8A' + \
                                 'BF 90 AF BC 8A BD 94 AF BC AA 95 80 AF 9F 80 AA' + \
                                 '95 BC BC BE 85 BF 8A BD BE 85 95 82 BF 0A 0A 0A' + \
                                 '00 10 95 B4 A8 88 9C A8 8C A8 80 94 A8 A8 8C A8' + \
                                 '8C A8 90 94 AC 84 0A 00 10 95 97 AF 80 95 AA B1' + \
                                 'AA 90 B5 AA AA BA AA B1 AA 8B 95 AA 0A 0A 00 11' + \
                                 '82 97 A8 8C A8 80 9C 84 94 94 94 9C 84 94 9C 94' + \
                                 'B4 A8 0A 00 12 95 AA B1 AA 90 B7 90 A5 85 95 B3' + \
                                 '95 95 B5 95 97 AF' )

        i = 0
        while i < len( rawLogo ):
            character = rawLogo[i]
            if character == 0:
                result += KCBasicUtils.HPOS % rawLogo[i+1]
                i += 1
            elif character == 0x0a:
                result += KCBasicUtils.controlCharsDict[character]
            elif character >= 0x41 and character <= 0x5a:
                result += chr(character)
            elif character >= 0x80 and character <= 0xBF:
                blockChar = None
                if format in KCBasicUtils.formatDicts and character in KCBasicUtils.formatDicts[format]:
                    blockChar = KCBasicUtils.formatDicts[format][character]
                if blockChar == None:
                    blockChar = '^%d^' % character
                else:
                    blockChar = chr(blockChar)
                result += blockChar
            else:
                statusPrinter.errorExit( 2, 'Illegal character $%02x found in rawLogo string' % character )
            i += 1
        
        return result
        
    def parseCharacter( character, escGroup, escChar, format, statusPrinter ):
        """
        Decodes a character (1-byte or 3-byte format).
            character       - 1st byte of a 3-byte escape sequence or the only byte in a 1-byte sequence
            escGroup        - 2nd byte of a 3-byte escape sequence or None.
            escChar         - 3rd byte of a 3-byte escape sequence or None
            format          - String that indicates the expected format the string will be returned in.
                              See parseString() documentation for details
            statusPrinter   - KCStatusPrinter for logging and errors
        """
        resultSnippet = None
        kcDispChar    = None    # If not None, a character that the KC can display using its char-set.
        if ( character < 0x20 or character == 0x7F ) and ( escGroup == None or escChar == None ):
            # Handle control characters or the ` (grave) character
            if character in KCBasicUtils.controlCharsDict:
                resultSnippet = KCBasicUtils.controlCharsDict[character]
        elif character != 27:
            kcDispChar = character
        elif escGroup != None and escChar != None:
            # The main escape sequence decoding block
            if escGroup >= 16 and escGroup <= 19 and escChar >= 3 and escChar <= 255:
                # Through experimentation, escChar == escChar MOD 64 except when 0, 1, and maybe 2
                # Mattel sometimes took advantage of this trick so it will be handled here.
                kcDispChar = ( ( escGroup & 0x03 ) << 6 ) | ( escChar & 0x3F )
            if escGroup == 20 and escChar >= 65 and escChar <= 103:
                resultSnippet = HPOS % ( escChar - 64 )
            if escGroup == 21 and escChar >= 65 and escChar <= 88:
                resultSnippet = '^VPOS_CURSOR(%d)^' % ( escChar - 64 )
            if escGroup == 22 and escChar >= 64 and escChar <= 102:
                resultSnippet = '^LMARGIN(%d)^' % ( escChar - 64 )
            if escGroup == 23 and escChar >= 65 and escChar <= 103:
                resultSnippet = '^RMARGIN(%d)^' % ( escChar - 64 )
            if escGroup == 24 and escChar >= 65 and escChar <= 88:
                resultSnippet = '^TMARGIN(%d)^' % ( escChar - 64 )
            if escGroup == 25 and escChar >= 65 and escChar <= 88:
                resultSnippet = '^BMARGIN(%d)^' % ( escChar - 64 )
            if escGroup == 26 and escChar >= 64 and escChar <= 128:
                if escChar == 64 or escChar == 128:
                    resultSnippet = 'SOLID_ON'
                elif escChar == 127:
                    resultSnippet = 'SOLID_OFF'
                else:
                    resultSnippet = '%d' % ( escChar - 64 )
                resultSnippet = '^BLINK_RATE(%s)^' % resultSnippet
            if escGroup == 27 and escChar >= 64 and escChar <= 127:
                resultSnippet = '^REPEAT_DELAY(%d)^' % ( escChar - 64 )
            if escGroup >= 28 and escGroup <= 29 and escChar >= 65 and escChar <= 102:
                resultSnippet = KCBasicUtils.hardcodedStrings[escChar-64][0]
                if resultSnippet != None:
                    if escGroup == 29:
                        # Capitalize the first letter
                        firstLetter = resultSnippet[:1]
                        if firstLetter.islower():
                            resultSnippet = firstLetter.upper() + resultSnippet[1:]
                if resultSnippet == None:
                    resultSnippet = KCBasicUtils.buildIntellivisionLogo( format, statusPrinter )
            if escGroup == 30 and escChar >= 65 and escChar <= 102:
                if escGroup == 30:
                    resultSnippet = KCBasicUtils.hardcodedStrings[escChar-64][1]
                if resultSnippet == None:
                    resultSnippet = KCBasicUtils.hardcodedStrings[escChar-64][0]
                    if resultSnippet != None:
                        # Make upper case
                        resultSnippet = resultSnippet.upper()
                    else:
                        resultSnippet = KCBasicUtils.buildIntellivisionLogo( format, statusPrinter )
            if escGroup == 31 and escChar >= 65 and escChar <= 127:
                flagValue   = escChar & 0x2F
                onOffString = 'OFF' if ( escChar & 0x10 ) == 0 else 'ON'
                # In theory, it is possible that _some_ flags can be combined but
                # this decoding is not supported here since it is not documented.
                if flagValue in KCBasicUtils.flagNames:
                    resultSnippet = KCBasicUtils.flagNames[flagValue]
                if resultSnippet != None:
                    resultSnippet = '^%s_%s^' % ( resultSnippet, onOffString )

        # If its a KC character, attempt to decode it.
        if kcDispChar != None:
            if kcDispChar in KCBasicUtils.formatDicts[format]:
                resultSnippet = chr( KCBasicUtils.formatDicts[format][kcDispChar] )
            elif escGroup == 18:
                resultSnippet = '^BOX_%02X_%s^' % ( escChar & 0x3F, \
                                                    bin( escChar & 0x3F ).lstrip('0b').rjust(6, '0')[::-1] )
            elif escGroup == 19:
                resultSnippet = '^BRAILLE_%02X_%s^' % ( escChar & 0x3F, \
                                                        bin( escChar & 0x3F ).lstrip('0b').rjust(6, '0')[::-1] )
        
        # If resultSnippet was not handled, then just print out the raw numbers in decimal
        if resultSnippet == None:
            if escGroup != None and escChar != None:
                resultSnippet = '^%d^^%d^^%d^' % ( character, escGroup, escChar )
            else:
                resultSnippet = '^%d^' % character

        return resultSnippet



class BinCfgFilePair:
    """
    Represents the BIN+CFG file pair that specify Master Component's memory data.
    """

    __SUFFIX_BIN       = '.bin'
    __SUFFIX_CFG       = '.cfg'
    __SUFFIX_LEN       = len( __SUFFIX_BIN )
    __KEY_MAPPING      = 'mapping'
    __KEY_NONE         = None      # Special case key for lines that PRECEDE the first section

    def __init__(self, fileNamesBase, memoryMap, canOverwriteFiles, statusPrinter ):
        """
        Initializer
           fileNameBase        - string path and filename of the BIN+CFG.  The ".bin" and ".cfg" will be appended if needed
           memoryMap           - MCMemoryMap
           canOverwriteFiles   - boolean of whether it is ok to overwrite existing files
           statusPrinter   - KCStatusPrinter for printing
        """
        self.memoryMap          = memoryMap
        self.fileNameBin        = self.getBaseFilename( fileNamesBase ) + self.__SUFFIX_BIN
        self.fileNameCfg        = self.getBaseFilename( fileNamesBase ) + self.__SUFFIX_CFG
        self.canOverwriteFiles  = canOverwriteFiles
        self.binData            = None
        self.cfgSections        = {}    # keys are section strings, values are lists of lines
        self.doAddCommandLine   = True
        self._printer           = statusPrinter
        self.queuedComments     = []

    def getBaseFilename( self, fileNamesBase ):
        """
        Returns the true base filename by removing the ".bin" and ".cfg" if necessary
        """
        if fileNamesBase.lower().endswith( self.__SUFFIX_BIN ):
            return fileNamesBase[:-self.__SUFFIX_LEN]
        if fileNamesBase.lower().endswith( self.__SUFFIX_CFG ):
            return fileNamesBase[:-self.__SUFFIX_LEN]
        return fileNamesBase
        
    def readFiles( self ):
        """
        Reads the BIN+CFG file pair
        """

        # Read in the BIN file
        self._printer.printStatus( 0, 'Opening BIN file "%s" ...' % self.fileNameBin )
        if not os.path.isfile(self.fileNameBin):
            self._printer.errorExit( 2, 'File "' + self.fileNameBin + '" is not a readable file.' )
        binFile = open( self.fileNameBin, 'rb' )
        self.binData = binFile.read()
        binFile.close()
        if len(self.binData) <= 0:
            self._printer.errorExit( 2, 'File "' + self.fileNameBin + '" contains no data' )
            
        # Read in the raw CFG file
        self._printer.printStatus( 0, 'Opening CFG file "%s" ...' % self.fileNameCfg )
        if not os.path.isfile(self.fileNameCfg):
            self._printer.errorExit( 2, 'File "' + self.fileNameCfg + '" is not a readable file.' )
        cfgFile = open( self.fileNameCfg, 'r' )
        cfgData = cfgFile.read()
        cfgFile.close()
        
        #
        # Parse the CFG file (at least partially)
        #
        # Mostly, lines after a section (ex: [vars]) are associated with that section.  Here are the exceptions:
        # 1.  Contiguous comments immediately BEFORE a section as associated that section.
        #     Blank lines and lines with non-comment data break contiguousness (i.e. these lines go with the PRIOR section, as per normal).
        # 2.  [mapping] section is treated special since it is the only section that is truly parsed.
        #     All other sections are just plain lines of text.
        # 3.  Corner case: blank and comment lines that appear before the 1st section are associated with that section.
        #
        reSectionName       = re.compile(r"\[([^\]]*)\]")
        reMappingLine       = re.compile(r"\$([0-9A-Fa-f]{1,4})\s*-\s*\$([0-9A-Fa-f]{1,4})\s*=\s*\$([0-9A-Fa-f]{1,4})\s*(.*)")
        sectionCurrent      = self.__KEY_NONE
        cfgLines = cfgData.splitlines(False)
        for i in range(0, len(cfgLines)):
            cfgLine         = cfgLines[i]
            appendLine      = False
            hasComment      = self.lineHasComment( cfgLine )
            cfgLineTrimmed  = self.trimCommentAndWhitespace( cfgLine )
            isEmpty         = len( cfgLineTrimmed ) == 0
            onlyComment     = hasComment and isEmpty
            
            # Core parsing block
            reSectionMatch = reSectionName.fullmatch( cfgLineTrimmed )
            if reSectionMatch != None:
                # Handler for parsing a section header (ex: [vars] or [mapping])
                sectionCurrent = reSectionMatch.group(1)
                if sectionCurrent not in self.cfgSections:
                    self.cfgSections[sectionCurrent] = []
            elif not isEmpty and sectionCurrent == self.__KEY_MAPPING:
                # Handler for lines in the [mapping] section
                reMappingMatch = reMappingLine.fullmatch( cfgLineTrimmed )
                if reMappingMatch == None:
                    self._printer.errorPrint( 'Unrecognized [mapping] line: ' + cfgLine )
                    self._printer.errorExit( 2, 'Unrecognized [mapping] line:\n' + cfgLine )
                if reMappingMatch.group(4) != None and len( reMappingMatch.group(4) ) > 0:
                    self._printer.errorExit( 2, 'Parser does not handle [mapping] lines with the extension of: "%s"' % reMappingMatch.group(4) )
                startOffset     = int( reMappingMatch.group(1), 16)
                lenInBytes      = ( int( reMappingMatch.group(2), 16) - startOffset + 1 ) * 2
                startAddress    = int( reMappingMatch.group(3), 16)
                startOffset     *= 2    # The 2x converts from WORD index into BYTE index
                self.memoryMap.writeByteBuffer( startAddress, self.binData, startOffset, lenInBytes, cfgLine )
            else:
                if sectionCurrent == self.__KEY_NONE and not self.__KEY_NONE in self.cfgSections:
                    self.cfgSections[sectionCurrent] = []
                self.cfgSections[sectionCurrent].append( cfgLine )
            
    def writeFiles( self ):
        """
        Writes the BIN+CFG file pair
        """
        # Open in the BIN file for writing
        self._printer.printStatus( 0, 'Opening BIN file "%s" for writing ...' % self.fileNameBin )
        if self.canOverwriteFiles == False and os.path.exists(self.fileNameBin):
            self._printer.errorExit( 2, 'File "' + self.fileNameBin + '" already exists.  Use --file-overwrite to force overwriting the file.' )
        binFile = open( self.fileNameBin, 'wb' )
            
        # Open in the CFG file for writing
        self._printer.printStatus( 0, 'Opening CFG file "%s" for writing ...' % self.fileNameBin )
        if self.canOverwriteFiles == False and os.path.exists(self.fileNameCfg):
            self._printer.errorExit( 2, 'File "' + self.fileNameCfg + '" already exists.  Use --file-overwrite to force overwriting the file.' )
        cfgFile = open( self.fileNameCfg, 'w' )
        
        self._printer.printStatus( 0, 'Writing to BIN and CFG files ...' )
        self.addCommandLineComment()
        for i in range( 0, len( self.queuedComments ) ):
            self.cfgSections[self.__KEY_NONE].insert( i+1, '; ' + self.queuedComments[i] ) # The +1 is so queued comments are inserted below the command-line
        if self.__KEY_MAPPING not in self.cfgSections:
            self.cfgSections[self.__KEY_MAPPING] = []
        sectionKeys = self.cfgSections.keys()
        isLastNoneLineBlank = False
        if self.__KEY_NONE in sectionKeys:
            for line in self.cfgSections[self.__KEY_NONE]:
                cfgFile.write( line + '\n' )
                isLastNoneLineBlank = ( len( line.strip() ) == 0 )
        if not isLastNoneLineBlank:
            cfgFile.write( '\n' )
        for sectionKey in sectionKeys:
            if sectionKey == self.__KEY_NONE:
                continue
            cfgFile.write( '[' + sectionKey + ']\n' )
            for line in self.cfgSections[sectionKey]:
                cfgFile.write( line + '\n' )
            if sectionKey == self.__KEY_MAPPING:
                self.writeMappingSection( binFile, cfgFile )
                    
        binFile.close()
        cfgFile.close()
        
    def appendCfg( self, otherBinCfg ):
        """
        Copies CFG data from another BinCfgFilePair
        """
        if otherBinCfg == None:
            return
        self.addCommandLineComment()
        otherKeys = otherBinCfg.cfgSections.keys()
        for otherKey in otherKeys:
            otherLines = otherBinCfg.cfgSections[otherKey].copy()
            if otherKey in self.cfgSections:
                self.cfgSections[otherKey] += otherLines
            else:
                self.cfgSections[otherKey] = otherLines
        #self.debugPrint()
        
    def writeMappingSection( self, binFile, cfgFile ):
        """
        Writes the section called 'mapping' to both the BIN file and CFG file
        """
        startAddress = None
        startOffset  = 0
        nextOffset   = 0
        for address in range( 0, self.memoryMap.SIZE ):
            isWritten = ( self.memoryMap.getWordState( address ) == self.memoryMap.STATE_WRITTEN )
            if isWritten:
                if startAddress == None:
                    startAddress = address
                nextOffset += 1
                binFile.write( self.memoryMap.readWord( address ).to_bytes( 2, byteorder="big", signed=False ) )
            else:
                if startAddress != None:
                    cfgFile.write( '$%04x - $%04x = $%04x\n' % ( startOffset, nextOffset-1, startAddress ) )
                    startOffset  = nextOffset
                    startAddress = None
        # Handle the case where data was written all the way up to $FFFF
        if startAddress != None:
            cfgFile.write( '$%04x - $%04x = $%04x\n' % ( startOffset, self.memoryMap.SIZE-1, startAddress ) )

    def addCommandLineComment( self ):
        """
        Adds the command-line to the [mapping] section.
        Can be called multiple times but only executes first time.
        """
        if self.doAddCommandLine == False:
            return
        self.doAddCommandLine = False
        commandLine = ";"
        for arg in sys.argv:
            if arg.find( " " ) >= 0:
                arg = '"' + arg + '"'
            commandLine += " " + arg
        if self.__KEY_NONE not in self.cfgSections:
            self.cfgSections[self.__KEY_NONE] = []
        self.cfgSections[self.__KEY_NONE].insert( 0, commandLine )

    def queueCommentsForWrite( self, linesOfText ):
        """
        Queues up one-line comment(s) that will be written out later to a file.
            linesOfText - Either a string or a list of strings of one-line comments
        """
        if isinstance( linesOfText, list):
            for i in range( 0, len( linesOfText ) ):
                self.queuedComments.append( linesOfText[i] )
        elif isinstance( linesOfText, str):
            self.queuedComments.append( linesOfText )
        else:
            self.queuedComments.append( str( linesOfText ) )

    def lineHasComment( self, lineText ):
        """
        Returns whether a line of text has a comment in it
        """
        return lineText.find(';') != -1
        
    def trimCommentAndWhitespace( self, lineText ):
        """
        Returns what is left after removing any comments and then removing any leading and trailing whitespace 
        """
        return lineText.split(';')[0].strip()
    
    def debugPrint(self):
        """
        Debug printing
        """
        #self._printer.printStatus( 0, self.cfgSections )
        sectionKeys = self.cfgSections.keys()
        if self.__KEY_NONE in sectionKeys:
            for line in self.cfgSections[self.__KEY_NONE]:
                self._printer.printStatus( 0, line )
        for sectionKey in sectionKeys:
            if sectionKey == self.__KEY_NONE:
                continue
            self._printer.printStatus( 0, '[' + sectionKey + ']' )
            for line in self.cfgSections[sectionKey]:
                self._printer.printStatus( 0, line )
    


class KCRecords:
    """
    Manager class for record files
    """

    def __init__(self, fileNamesPattern, startIndex, endIndex, statusPrinter ):
        """
        Initializer
          fileNamesPattern - printf-style string path and name.  It is expected to accept 0 or 1 integer values.
                            If the string accepts NO integer values, then it is exact path and file name.
                            If it accepts ONE integer value, then the formatted values from startIndex to endIndex
                            are used.
                            If it is the empty string or None, then the default of "record_%04d.bin" is used.
          startIndex      - integer of the starting record number (i.e. the first value used in NNNN.bin)
          endIndex        - integer of the last record number to be used (i.e. the last value used in NNNN.bin).
                            Use -1 to indicate that there is no end. 
          statusPrinter   - KCStatusPrinter for printing
        """
        if fileNamesPattern == None or fileNamesPattern == "":
            self.fileNamesPattern = "record_%04d.bin"
        else:
            self.fileNamesPattern = fileNamesPattern
        self.percentCount   = self.fileNamesPattern.count('%')
        self.startIndex     = startIndex
        self.endIndex       = endIndex
        self.currentIndex   = -1
        self._printer       = statusPrinter

        percentDoubleCount  = self.fileNamesPattern.count('%%')
        if self.percentCount > 2 and self.percentCount / 2 != percentDoubleCount:
            self._printer.errorExit( 2, 'Filename base of "%s" is invalid' % fileNamesPattern )
            
        if percentDoubleCount > 0:
            self.fileNamesPattern = self.fileNamesPattern.replace( '%%', '%' )
            self.percentCount   = 0
    
    def getNextRecordBuffer(self):
        """
        Returns the next record file's byte buffer
        IMPORTANT: None is returns if too many records are attempted to be opened
        """
        filename = ""
        if self.percentCount == 1:
            if self.currentIndex == -1:
                self.currentIndex = self.startIndex
            else:
                self.currentIndex += 1                
            if self.endIndex != -1 and self.currentIndex > self.endIndex:
                return None
                
            fileName = self.fileNamesPattern % self.currentIndex
        else:
            if self.currentIndex != -1:
                return None
            fileName = self.fileNamesPattern
            self.currentIndex = 0
           
        self._printer.printStatus( 0, 'Opening "%s" ...' % fileName )
        if not os.path.isfile(fileName):
            self._printer.errorExit( 2, 'File "' + fileName + '" is not a readable file.' )
        
        fileObj = open( fileName, 'rb' )
        binData = fileObj.read()
        fileObj.close()
        return binData



class KCAbstractRecordReader:
    """
    Abstract class that reads and parses KC's records
    Derived classes must implement:
        def readRawByte(self):      # Returns the next RAW byte from a record file or None if the end has been reached
    """

    _CHUNK_BYTES    = 0x40
    KC_TO_MC_OFFSET = 0x8000
    _KC_ADDRESS_END = 0x3fff
    ADDRESS_START   = KC_TO_MC_OFFSET
    ADDRESS_END     = KC_TO_MC_OFFSET + _KC_ADDRESS_END

    def __init__(self, memoryMap, fileNamesPattern, startIndex, endIndex, statusPrinter ):
        """
        Initializer
          memoryMap       - MCMemoryMap that will be updated with BASIC data
          fileNamesPattern- string path and name that prefixes NNNN.bin (where NNNN is a decimal number).
                            If empty or None, then the default of "record_" is used.
          startIndex      - integer of the starting record number (i.e. the first value used in NNNN.bin)
          endIndex        - integer of the last record number to be used (i.e. the last value used in NNNN.bin).
                            Use -1 to indicate that there is no end. 
          statusPrinter   - KCStatusPrinter for printing
        """
        self.memoryMap                  = memoryMap
        self.records                    = KCRecords( fileNamesPattern, startIndex, endIndex, statusPrinter )
        self._printer                   = statusPrinter
        # Current data variables
        self._binData                   = self.records.getNextRecordBuffer()
        self._binIndex                  = 0
        # Size and offset variables and constants

    def readRawWord(self):
        """
        Returns the next RAW little-endian word from a record file or None if the end has been reached
        """
        data1 = self.readRawByte()
        data2 = self.readRawByte()
        if data1 == None or data2 == None:
            return None
        return ( (data1 & 0xff) << 8 ) | ( data2 & 0xff )

    def readLowByte(self):
        """
        Returns the low byte from the next word from a record file or None if the end has been reached
        """
        data = self.readRawWord()
        if ( data & 0xfc00 ) != 0x0000:
            self._printer.errorExit( 3, "Read illegal upper byte value of $%04x at offset $%04x" % (data, self._binIndex-2) )
        return data & 0xff

    def readLowBytesAsWord(self):
        """
        Returns the little-endian word from low bytes of the next 2 words from a record file
        or None if the end has been reached
        """
        data1 = self.readLowByte()
        data2 = self.readLowByte()
        if data1 == None or data2 == None:
            return None
        return ( (data2 & 0xff) << 8 ) | ( data1 & 0xff )
        
    def printAnyData(self, indentLevel, startOffset, lengthBytes):
        """
        Prints any section of data from the record
            indentLevel     - Integer of how much to indent the printing
            startOffset     - Integer of starting offset into the binary data
            lengthBytes     - Integer of how many bytes to print
        """
        if self._binData == None or startOffset < 0 or lengthBytes <= 0:
            return

        if startOffset+lengthBytes > len( self._binData ) :
            self._printer.errorExit( 3, "Attempt to read more data than remains.  Requested to read up to index %d when there are only %d bytes" % \
                                        ( startOffset+lengthBytes, len( self._binData )  ) )

        lengthChunks = lengthBytes // self._CHUNK_BYTES
        self._printer.printStatus( indentLevel, "Length = $%x (%d) bytes or $%x (%d) chunks." % \
                                                ( lengthBytes, lengthBytes, lengthChunks, lengthChunks ) )
        line = None
        text = None
        for i in range( startOffset, len( self._binData ) ):
            if line == None:
                line = "$%04x :" % i
                text = "    "
            line += " %02x" % self._binData[i]
            # Append a printable ASCII character or a '.'
            text += chr(self._binData[i]) if self._binData[i] >= 0x20 and self._binData[i] <= 0x7E else '.'                
            if ( i - startOffset ) % 16 == 15:
                line += text
                self._printer.printStatus( indentLevel, line )
                line = None
                text = None
        if line != None:
            line = line.ljust(55)   # Pad out the string with enough spaces
            line += text
            self._printer.printStatus( indentLevel, line )

    def printNextData(self, indentLevel, lengthBytes):
        """
        Prints the next section of data from the record
            indentLevel     - Integer of how much to indent the printing
            lengthBytes     - Integer of how many bytes to print
        """
        self.printAnyData( indentLevel, self._binIndex, lengthBytes )
        
    def dumpUnreadData(self, indentLevel):
        """
        If there is unread data left in the buffer, print it out in hex
        """
        if self._binData == None or self._binIndex >= len( self._binData ):
            return
            
        lengthBytes     = len( self._binData ) - self._binIndex
        self._printer.printStatus( indentLevel, "The following data not read from the file:")
        self.printAnyData( indentLevel+1, self._binIndex, lengthBytes )



class KCBasicRecordReader(KCAbstractRecordReader):
    """
    Class that reads and parses KC's BASIC records
    """

    # The following are used to get info on different blocks of BASIC-program related memory
    BLOCK_TYPE_PROGRAM         = 'program'
    BLOCK_TYPE_SCALARS         = 'scalars'
    BLOCK_TYPE_ARRAYS          = 'arrays' 
    BLOCK_TYPE_DYNA_STRINGS    = 'strings'

    __MAX_PAYLOAD_CHUNKS       = 0x40
    __MAX_PAYLOAD_BYTES        = KCAbstractRecordReader._CHUNK_BYTES * __MAX_PAYLOAD_CHUNKS
    __BASIC_ADDRESS_START      = KCAbstractRecordReader.KC_TO_MC_OFFSET + 0x0801
    __IS_FIRST_DATA            = 0x05
    __HAS_MORE_DATA            = 0xe4
    __TYPE_VARIABLES           = 0x01
    __TYPE_PROGRAM             = 0x02
    __HEADER_PROGRAM_DECLES    = "headerProgramDecles"
    __HEADER_SCALARS_DECLES    = "headerScalarsDecles"
    __HEADER_ARRAYS_DECLES     = "headerArraysDecles" 
    __HEADER_STRINGS_DECLES    = "headerStringsDecles"
    __HEADER_STRINGS_ADDRESS   = "headerStringsAddress"
    __ADDR_BASIC_PROG_START    = 0x8029    # Start of BASIC program (value $0801)
    __ADDR_SCALARS_START       = 0x802b    # Start of Scalar variables
    __ADDR_ARRAYS_START        = 0x802d    # Start of Array variables
    __ADDR_ARRAYS_END          = 0x802f    # End of Array variables (first byte after array)
    __ADDR_DYNA_STRING_START   = 0x8031    # Start of dynamic string stack
    
    def __init__(self, memoryMap, isROData, fileNamesPattern, startIndex, endIndex, statusPrinter ):
        """
        Initializer
          memoryMap       - MCMemoryMap that will be updated with BASIC data
          isROData        - boolean for whether the records are from a Read-Only track (True) or Read-Write track (False)
          fileNamesPattern- string path and name printf-string.  See KCRecords for details.
          startIndex      - integer of the starting record number (i.e. the first value used in NNNN.bin)
          endIndex        - integer of the last record number to be used (i.e. the last value used in NNNN.bin).
                            Use -1 to indicate that there is no end. 
          statusPrinter   - KCStatusPrinter for printing
        """
        KCAbstractRecordReader.__init__(self, memoryMap, fileNamesPattern, startIndex, endIndex, statusPrinter )
        self.isROData                   = isROData
        self.__HEADER_START             = self._CHUNK_BYTES if isROData else 0x00
        self.__HEADER_END               = self.__HEADER_START + self._CHUNK_BYTES
        self.__MAX_RECORD_BYTES         = self.__HEADER_END + self.__MAX_PAYLOAD_BYTES
        self.__headerPayloadEnd         = None
        self.__headerFirstData          = None
        self.__headerMoreData           = None
        self.__headerType               = None
        # Stores a copy of the first record's header.  Errors if a record is loaded where the values change.  Order matters.
        self.__firstRecordHeader = {   \
            self.__HEADER_PROGRAM_DECLES:  None, \
            self.__HEADER_SCALARS_DECLES:  None, \
            self.__HEADER_ARRAYS_DECLES:   None, \
            self.__HEADER_STRINGS_DECLES:  None, \
            self.__HEADER_STRINGS_ADDRESS: None, \
        }
        # Similar to above but is a modified copy of the above since __TYPE_VARIABLES records are
        # allowed to be shifted in memory (so that variables start immediately after a program).
        self.__inMemoryHeaders          = self.__firstRecordHeader.copy()
        self.__loggableMessages         = []

    def parse(self):
        """
        Parses the KC's BASIC records
        """
        self.parseHeader()
        
        size    = self.__inMemoryHeaders[ self.__HEADER_PROGRAM_DECLES ]
        address = self.readBlockIntoMemoryMap( self.BLOCK_TYPE_PROGRAM, self.__BASIC_ADDRESS_START, size )
        if address == None:
            return
        size    = self.__inMemoryHeaders[ self.__HEADER_SCALARS_DECLES ]
        address = self.readBlockIntoMemoryMap( self.BLOCK_TYPE_SCALARS, address, size )
        if address == None:
            return
        size    = self.__inMemoryHeaders[ self.__HEADER_ARRAYS_DECLES ]
        address = self.readBlockIntoMemoryMap( self.BLOCK_TYPE_ARRAYS, address, size )
        if address == None:
            return
        size    = self.__inMemoryHeaders[ self.__HEADER_STRINGS_DECLES ]
        address = self.__inMemoryHeaders[ self.__HEADER_STRINGS_ADDRESS ] + self.KC_TO_MC_OFFSET
        address = self.readBlockIntoMemoryMap( self.BLOCK_TYPE_DYNA_STRINGS, address, size )
        if address == None:
            return
            
    def getBlockInfo( memoryMap, blockType ):
        """
        Returns info on info on blocks of BASIC-program related memory
            blockType   - String that is one of the BLOCK_TYPE_ constants
        Return value - An object containing 'address' and 'length', both with integer values.
        """
        addressStart = None
        addressEnd   = None
        if blockType == KCBasicRecordReader.BLOCK_TYPE_PROGRAM:
            addressStart = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_BASIC_PROG_START )
            addressEnd   = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_SCALARS_START )
        elif blockType == KCBasicRecordReader.BLOCK_TYPE_SCALARS:
            addressStart = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_SCALARS_START )
            addressEnd   = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_ARRAYS_START )
        elif blockType == KCBasicRecordReader.BLOCK_TYPE_ARRAYS:
            addressStart = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_ARRAYS_START)
            addressEnd   = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_ARRAYS_END )
        elif blockType == KCBasicRecordReader.BLOCK_TYPE_DYNA_STRINGS:
            addressStart = KCBasicRecordReader.safeReadMemoryMapLowBytesAsWord( memoryMap, KCBasicRecordReader.__ADDR_DYNA_STRING_START)
            addressEnd   = KCAbstractRecordReader._KC_ADDRESS_END + 1
        else:
            return None
            
        if addressStart == None or addressEnd == None or addressStart > addressEnd:
            return None
            
        addressStart += KCAbstractRecordReader.KC_TO_MC_OFFSET
        addressEnd   += KCAbstractRecordReader.KC_TO_MC_OFFSET

        class Result: pass
        result = Result()
        result.address = addressStart
        result.length  = addressEnd - addressStart
        return result

    def safeReadMemoryMapLowBytesAsWord( memoryMap, address ):
        """
        Reads the low bytes from memoryMap as a word or returns None if the low bytes have not been written to
            address     - Integer value of address
        """
        if memoryMap.getWordState( address     ) != MCMemoryMap.STATE_WRITTEN or \
           memoryMap.getWordState( address + 1 ) != MCMemoryMap.STATE_WRITTEN:
            return None
        return memoryMap.readLowBytesAsWord( address )
    
    def readBlockIntoMemoryMap( self, blockType, address, decleCount ):
        """
        Reads a block of data into the memory map (depending on __headerType and blockType).
        Returns the address following the last write or None if no more data can be read.
        Note that blockType must be one of the BLOCK_TYPE_ values
        """
        if  ( blockType == self.BLOCK_TYPE_PROGRAM      and self.__headerType != self.__TYPE_PROGRAM   ) or \
            ( blockType == self.BLOCK_TYPE_SCALARS      and self.__headerType != self.__TYPE_VARIABLES ) or \
            ( blockType == self.BLOCK_TYPE_ARRAYS       and self.__headerType != self.__TYPE_VARIABLES ) or \
            ( blockType == self.BLOCK_TYPE_DYNA_STRINGS and self.__headerType != self.__TYPE_VARIABLES ):
            # Skip any real processing.
            return address + decleCount
        if decleCount == 0:
            # Nothing to copy
            return address
        self._printer.printStatus( 1, 'Processing %s section ...'  % blockType )
        for i in range( 0, decleCount ):
            # Actually copy the data
            decle = self.readRawWord()
            if decle == None:
                self._printer.printStatus( 1, "INFO: Could not read all data for %s section.  Only read $%04x of $%04x decles." % \
                                              ( blockType, i, decleCount ) )
                return None
            self.memoryMap.writeWord( address, decle )
            address += 1
        return address
        
    def readRawByte(self):
        """
        Returns the next RAW byte from a record file or None if the end has been reached
        """
        if self.__headerPayloadEnd == None or self._binIndex >= self.__headerPayloadEnd:
            if self.__headerMoreData == 0x00:
                return None
            else:
                self._binIndex = 0
                self._binData  = self.records.getNextRecordBuffer()
                if self._binData == None:
                    self._printer.printStatus( 1, 'WARNING: Ended record file reading early.  Truncation likely.' )
                    return None
                self.parseHeader()
        data = self._binData[self._binIndex]
        self._binIndex += 1
        return data
    
    def parseHeader(self):
        """
        Parses a header after a new record file has just been opened.
        It extracts header values and compared them to any previous file header values.
        """
        if self._binIndex != 0:
            self._printer.errorExit( 3, "Illegal call to parseHeader" )
        if self.__HEADER_END > len( self._binData ):
            self._printer.errorExit( 3, "Record file too short to contain the proper header.  Was %d bytes, needed %d" % \
                                        (len( self._binData ), self.__HEADER_END ) )
        # Above check guarantees that read*() will never return None
        
        if self.__headerPayloadEnd == None:
            self._printer.printStatus( 1, "Processing first header and special memory locations ..." )
        else:
            self._printer.printStatus( 1, "Processing next header (BASIC values are identical to previous header's) ..." )
        
        
        self.__headerPayloadEnd = 0xfffffff     # Temp setting this to prevent recursion
        if self.__HEADER_START > 0:
            # Just discard the non-BASIC part of the header.
            for i in range( 0, self.__HEADER_START ):
                self.readRawByte()
                
        self.__headerPayloadEnd = self.readLowBytesAsWord()
        self._printer.printStatus( 2, "Record size (chunks)       : %d" % self.__headerPayloadEnd )
        if self.__headerPayloadEnd > self.__MAX_PAYLOAD_CHUNKS:
            self._printer.errorExit( 3, 'BASIC payload chunk length (%d) exceeds max (%d).' % \
                                        (  self.__headerPayloadEnd, self.__MAX_PAYLOAD_CHUNKS ) )
        self.__headerPayloadEnd = self.__headerPayloadEnd * self._CHUNK_BYTES + self.__HEADER_END
        if self.__headerPayloadEnd > len( self._binData ):
            self._printer.errorExit( 3, 'BASIC header specified record length (%d bytes) is greater than the file\'s length (%d bytes)' % \
                                        (self.__headerPayloadEnd, len( self.binData ) ) )
        
        ZERO_WORD_COUNT = 10
        for i in range( 0, ZERO_WORD_COUNT ):
            expectZero = self.readRawWord()
            if expectZero != 0:
                self._printer.printStatus( 2, "WARNING: Expected $0000 for header word %d but got $%04x instead.  " \
                                              "Please report this to the Intellivision Keyboard Component experts." % ( i+1, expectZero ) )
        
        headerFirstData = self.readLowByte()
        self._printer.printStatus( 2, "Record isFirst flags       : $%02x" % headerFirstData )
        if self.__headerFirstData == None:
            if headerFirstData != self.__IS_FIRST_DATA:
                self._printer.errorExit( 3, 'BASIC first header\'s first-data word was illegal value of $%04x' % headerFirstData )
        elif headerFirstData != 0x00:
            self._printer.errorExit( 3, 'BASIC continuation header\'s first-data word was illegal value of $%04x' % headerFirstData )
        self.__headerFirstData = headerFirstData
        
        headerMoreData = self.readLowByte()
        self._printer.printStatus( 2, "Record moreData flags      : $%02x" % headerMoreData )
        if headerMoreData != self.__HAS_MORE_DATA and headerMoreData != 0x00:
            self._printer.errorExit( 3, 'BASIC header\'s more-data word was illegal value of $%04x' % headerMoreData )
        elif headerMoreData == 0x00 and self.__headerPayloadEnd >= self.__MAX_PAYLOAD_BYTES:
            self._printer.errorExit( 3, 'BASIC last record had illegal length of %d' % self.__headerPayloadEnd )
        self.__headerMoreData = headerMoreData
        
        forceOverwrite = self.parseIdenticalRecordHeaderValues()
                  
        # Poke values into magic locations.  Addresses are MC addresses, but the values are KC addresses.
        # Address values are in little-endian format.
        # IMPORTANT: Not are all known.  These might not be adequate to load a BASIC program back into a KC
        value = self.__BASIC_ADDRESS_START - self.KC_TO_MC_OFFSET
        self.memoryMap.writeLowBytesAsWord( self.__ADDR_BASIC_PROG_START, value )                     # 8029: start of BASIC program (value $0801)
        value += self.__inMemoryHeaders[self.__HEADER_PROGRAM_DECLES]
        self.memoryMap.writeLowBytesAsWord( self.__ADDR_SCALARS_START, value, forceOverwrite )        # 802B: start of Scalar variables
        value += self.__inMemoryHeaders[self.__HEADER_SCALARS_DECLES]
        self.memoryMap.writeLowBytesAsWord( self.__ADDR_ARRAYS_START, value, forceOverwrite )         # 802D: start of Array variables
        value += self.__inMemoryHeaders[self.__HEADER_ARRAYS_DECLES]
        self.memoryMap.writeLowBytesAsWord( self.__ADDR_ARRAYS_END, value, forceOverwrite )           # 802F: ending byte of Array variables
        value = self.__inMemoryHeaders[self.__HEADER_STRINGS_ADDRESS]
        self.memoryMap.writeLowBytesAsWord( self.__ADDR_DYNA_STRING_START, value, forceOverwrite )    # 8031: start of dynamic string stack
        
    def parseIdenticalRecordHeaderValues( self ):
        """
        Reads header values that should be identical across headers, checks if the latest are the same as previous records, and copies
        the values (with adjustments, if necessary).
        It returns whether memory overwriting can be forced
        """
        forceOverwrite = False
        isFirstHeader  = ( self.__firstRecordHeader[self.__HEADER_PROGRAM_DECLES] == None )
    
        # Read and check against prior header
        headerType = self.readLowByte()
        if isFirstHeader:
            self._printer.printStatus( 2, "BASIC type                 : %d" % headerType )
        if headerType != self.__TYPE_VARIABLES and headerType != self.__TYPE_PROGRAM:
            self._printer.errorExit( 3, 'BASIC header\'s type word was illegal value of $%04x' % headerType )
        if self.__headerType != None and self.__headerType != headerType:
            self._printer.errorExit( 3, 'BASIC header\'s type changed from %02x to %02x' % ( self.__headerType, headerType ) )
        self.__headerType = headerType

        OFTEN_ZERO_WORD_COUNT = 7
        for i in range( 0, OFTEN_ZERO_WORD_COUNT ):
            expectZero = self.readRawWord()
            if expectZero != 0:
                self._printer.printStatus( 2, "INFO: Expected $0000 for header word %d but got $%04x instead.  " + \
                                              "This sometimes happens and is unexplained at this time." % ( i+0x0F, expectZero ) )
                
        for headerName in self.__firstRecordHeader.keys():
            data = self.readLowBytesAsWord()
            if isFirstHeader:
                self._printer.printStatus( 2, "BASIC %-20s : $%04x (%d)" % (headerName, data, data ) )
            if self.__firstRecordHeader[headerName] != None and data != self.__firstRecordHeader[headerName]:
                self._printer.errorExit( 3, 'Latest header does not match previous headers.  %s is $%04x but was previously $%04x' % \
                                            ( headerName, data, self.__firstRecordHeader[headerName]) )
            self.__firstRecordHeader[headerName] = data
            
        # Copy values
        for headerName in self.__firstRecordHeader.keys():
            self.__inMemoryHeaders[headerName] = self.__firstRecordHeader[headerName]
            
        # Adjust the copy, if necessary
        if self.__headerType == self.__TYPE_VARIABLES:
            # Different programs can load identical records with VLOD.  Need to shift the addresses if a program is already present.
            # RAM dumps show "start of Scalar variables" butts against programs but "Family Budgeting" has two different programs
            # with DIFFERENT lengths that can load the SAME VLOD/VSAV records.
            if self.memoryMap.getWordState( self.__ADDR_BASIC_PROG_START      ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_BASIC_PROG_START + 1  ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_SCALARS_START         ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_SCALARS_START + 1     ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_ARRAYS_START          ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_ARRAYS_START + 1      ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_ARRAYS_END            ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_ARRAYS_END + 1        ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_DYNA_STRING_START     ) == self.memoryMap.STATE_WRITTEN and \
               self.memoryMap.getWordState( self.__ADDR_DYNA_STRING_START + 1 ) == self.memoryMap.STATE_WRITTEN:
                # Shift the data to align to the pre-existing program.
                forceOverwrite = True
                newScalarsStart = self.memoryMap.readLowBytesAsWord( self.__ADDR_SCALARS_START ) - ( self.__BASIC_ADDRESS_START - self.KC_TO_MC_OFFSET )
                if isFirstHeader and self.__inMemoryHeaders[self.__HEADER_PROGRAM_DECLES] != newScalarsStart:
                    message1 = "INFO: Loading VSAV/VLOD data into existing memory map."
                    message2 = "    Shifting start address of variables from $%04x to existing $%04x." % \
                               ( self.__inMemoryHeaders[self.__HEADER_PROGRAM_DECLES], newScalarsStart )
                    self._printer.printStatus( 1, message1 )
                    self._printer.printStatus( 1, message2 )
                    self.__loggableMessages.append( message1 )
                    self.__loggableMessages.append( message2 )
                self.__inMemoryHeaders[self.__HEADER_PROGRAM_DECLES] = newScalarsStart
        
        # Finally check that the header values don't violate memory limitations
        stringsEndAddress = self.KC_TO_MC_OFFSET + \
                            self.__inMemoryHeaders[self.__HEADER_STRINGS_ADDRESS] + \
                            self.__inMemoryHeaders[self.__HEADER_STRINGS_DECLES] 
        if stringsEndAddress > self.ADDRESS_END:
            self._printer.errorExit( 3, 'String table in BASIC header extends past end of memory range' )
        totalBasicDecles = self.__inMemoryHeaders[self.__HEADER_PROGRAM_DECLES] + \
                           self.__inMemoryHeaders[self.__HEADER_SCALARS_DECLES] + \
                           self.__inMemoryHeaders[self.__HEADER_ARRAYS_DECLES]  + \
                           self.__inMemoryHeaders[self.__HEADER_STRINGS_DECLES]
        if totalBasicDecles > self.ADDRESS_END - self.__BASIC_ADDRESS_START + 1:
            self._printer.errorExit( 3, 'Total BASIC structures in header exceed allowed memory range' )

        return forceOverwrite

    def getLoggableMessages(self):
        """
        Returns a list of loggable messages
        """
        return self.__loggableMessages



class KCRODataRecordReader(KCAbstractRecordReader):
    """
    Class that reads and parses KC's Read-Only records
    """

    _BLOCK_COUNT       = 3

    def __init__(self, memoryMap, fileNamesPattern, startIndex, endIndex, isTruncationOk, statusPrinter, isShortLogging ):
        """
        Initializer
          memoryMap       - MCMemoryMap that will be updated with BASIC data
          fileNamesPattern- string path and name pattern.  See KCRecords for details
          startIndex      - integer of the starting record number (i.e. the first value used in NNNN.bin)
          endIndex        - integer of the last record number to be used (i.e. the last value used in NNNN.bin).
                            Use -1 to indicate that there is no end. 
          isTruncationOk  - Boolean whether truncated records are ok (versus causing an error).
          statusPrinter   - KCStatusPrinter for printing
          isShortLogging  - Enables shorter / less verbose logging
        """
        KCAbstractRecordReader.__init__(self, memoryMap, fileNamesPattern, startIndex, endIndex, statusPrinter )
        self.isTruncationOk     = isTruncationOk
        self.isShortLogging     = isShortLogging
        self.recordNum          = None
        self.recordChunks       = None
        self._blocks            = []

    def parse(self):
        """
        Parses the KC's BASIC records
        """
        while True:
            self.parseHeader()
            for i in range(0, self._BLOCK_COUNT):
                self.processHeaderBlock(i)
            self.dumpUnreadData(1)
            
            self._binData  = self.records.getNextRecordBuffer()
            if self._binData == None:
                break
            self._binIndex = 0
       
    def readRawByte(self):
        """
        Returns the next RAW byte from a record file or None if the end has been reached
        """
        if self._binIndex >= len( self._binData ):
            return None
        data = self._binData[self._binIndex]
        self._binIndex += 1
        return data
    
    def parseHeader(self):
        """
        Parses a header after a new record file has just been opened.
        """

        #  Latest Interpretation of header:
        #      Field types (stripped out upper byte/bits of the decle since it is not used, this header data is for the 6502)    
        #      Offset(h)  0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
        #      --------- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
        #      00000000  rn rn le le f1 00 00 d1 d1 c1 c1 p1 p1 f2 00 00
        #      00000010  d2 d2 c2 c2 p2 p2 f3 00 00 d3 d3 c3 c3 p3 p3 cs
        #      
        #  rn = record number
        #  le = length of record measured in chunks (includes header chunk, if zero then maybe ignore header)
        #  f# = flags, only values 00 and 04 observed, meanings unknown
        #  00 = only zero constants observed
        #  d# = destination address for the data, if value is 0000 then write nothing and just skip the chunks
        #  c# = number of chunks to write, starting at destination address
        #  p# = likely poke a value at this address, the value is likely the destination address.  If poke address is 0000, then likely don't poke.
        #  cs = checksum value (sum of entire header should equal 00)
        #  
        #  Note f# = 04 always has d# field as 0000.  Two examples of this:
        #      f# 0000 d#d# c#c# p#p#
        #      -- ---- ---- ---- ----
        #      04 0000 0000 0004 a40e
        #      04 0000 0000 0026 0000
        
        if len(self._binData) < self._CHUNK_BYTES:
            self._printer.errorExit( 4, "Record is shorter (%d bytes) than the length of a header" % ( len(self._binData), self._CHUNK_BYTES ) )

        # Check the checksum
        
        checksummedBytes = self._binData[:self._CHUNK_BYTES]
        checksum = 0
        for i in range( 1, self._CHUNK_BYTES, 2 ):
            checksum += self._binData[i]
        checksum &= 0xff
        if checksum != 0:
            self._printer.errorExit( 4, "Header's checksum was $%02x instead of $00 (only odd bytes are summed)" % checksum )

        # Parse general header fields
        
        recordNum = self.readLowBytesAsWord()
        self._printer.printStatus( 1, "Record number        : %d" % recordNum )
        if self.recordNum != None and recordNum != self.recordNum + 1:
            self._printer.errorExit( 4, "Non-sequential record number.  Read %d but next was expected to be %d" % \
                                        (recordNum, self.recordNum + 1 ) )
        self.recordNum = recordNum
        
        self.recordChunks  = self.readLowBytesAsWord()
        self._printer.printStatus( 1, "Record chunks        : $%04x (%d)" % (self.recordChunks, self.recordChunks) )
        if self.recordChunks * self._CHUNK_BYTES > len( self._binData ):
            message = "Header's chunk length field ($%04x) indicates %d decles long but the file was only %d bytes long" % \
                      ( self.recordChunks, self.recordChunks * self._CHUNK_BYTES, len( self._binData ) )
            if self.isTruncationOk:
                self._printer.printStatus( 2, "WARNING: " + message )
            else:
                self._printer.errorExit( 4, message )
                                        
        # Parse the 3 header blocks
        self._blocks = []
        for i in range(0, self._BLOCK_COUNT):
            self._blocks.append( KCRODataRecordReader.KCHeaderBlock( self._printer, \
                                                                     i, \
                                                                     self.readLowByte(), \
                                                                     self.readLowBytesAsWord(), \
                                                                     self.readLowBytesAsWord(), \
                                                                     self.readLowBytesAsWord(), \
                                                                     self.readLowBytesAsWord() ) )
            self._blocks[i].printStatus( 1, not self.isShortLogging )
            self._blocks[i].validate()
        
        # Read the checksum (just for alignment purposes, already handled it)
        ignoredChecksum = self.readLowByte()

    def processHeaderBlock( self, blockIndex ):
        """
        Processes a single header block.  Each record's header contains 3 blocks.  parseHeader() must have been called prior.
            blockIndex - Integer in range of [0,2].  Indicates which block to parse.
        """
        block = self._blocks[blockIndex]
        lengthBytes = block.lengthChunks * block.CHUNK_BYTES
        if block.type == block.TYPE_BULK_COPY:
            if block.lengthChunks != 0:
                isHighRange = block.isAddressHighRange( block.destAddress )
                if isHighRange == False:
                    self._printer.printStatus( 1, "WARNING: Low range destination address seen.  Assuming that only low-byte of each decle written.  Assumption could be wrong." )
                baseAddress = block.makeAddressHighRange( block.destAddress )
                for i in range( 0, lengthBytes // 2 ):
                    highByte = self.readRawByte() & 0xff
                    lowByte  = self.readRawByte() & 0xff
                    # If low address range, only the low byte value of decle is written
                    highByte = highByte if isHighRange else 0x00
                    self.memoryMap.writeWord( baseAddress+i, ( highByte << 8 ) | lowByte )
            if block.pokeAddress != block.ADDR_NONE:
                self._printer.printStatus( 1, "Handling poke addresses not yet implemented (address = $%04x).  Ignoring." % block.pokeAddress )
        elif block.type == block.TYPE_SKIP_DATA:
            if block.lengthChunks != 0:
                # Print block of data to screen but then read it to throw it away
                if not self.isShortLogging:
                    self._printer.printStatus( 1, "Skipping the following data:" )
                    self.printNextData(2, lengthBytes)
                for i in range( 0, lengthBytes ):
                    self.readRawByte()
            if block.pokeAddress != block.ADDR_NONE:
                self._printer.printStatus( 1, "Handling poke addresses not yet implemented (address = $%04x).  Ignoring." % block.pokeAddress )
        else:
            self._printer.errorExit( 4, 'Header block type of $%02x is not recognized.' % self.type )

        
    class KCHeaderBlock:
        """
        Class container for header block values with some utility methods
        """

        CHUNK_BYTES        = 0x40
        MAX_CHUNKS         = 2 * 0x4000 // CHUNK_BYTES      # "2 *" to convert bytes to decles, 0x4000 is decle address range's size.
        TYPE_BULK_COPY     = 0
        TYPE_SKIP_DATA     = 4
        ADDR_NONE          = 0x0000
        LOW_ADDR_MIN       = 0x0400                                 # Actual legal range of low address is unsure.  It could be 0x0000-0x3fff.
        LOW_ADDR_MAX       = 0x05ff                                 # Suspect that low range means "copy only the low byte of each decle"
        HIGH_ADDR_MIN      = KCAbstractRecordReader.KC_TO_MC_OFFSET # while high range means "copy entire decle".  This only is a loose guess.
        HIGH_ADDR_MAX      = KCAbstractRecordReader.ADDRESS_END

        def __init__( self, statusPrinter, index, type, padWord, destAddress, lengthChunks, pokeAddress ):
            """
            Initializer
                index           - Integer index number of the block within the larger header
                type            - Byte value for the type
                padWord         - Word value expected to be 0
                destAddress     - Word of starting address data should be written to
                lengthChunks    - Word of the data length, measured in chunks
                pokeAddress     - Word of address where a value should be poked (like the destAddress)
            """
            self._printer           = statusPrinter
            self.index              = index
            self.type               = type
            self.padWord            = padWord
            self.destAddress        = destAddress
            self.lengthChunks       = lengthChunks
            self.pokeAddress        = pokeAddress
            
        def printStatus( self, indentLevel, isLongFormat ):
            """
            Print (at 'status' level) the current state
                indentLevel     - Integer for the printing indentation level
                isLongFormat    - Boolean for whether long format (or short format) should be used.
            """
            if isLongFormat:
                self._printer.printStatus( indentLevel,   'Header block %d:' % self.index )
                self._printer.printStatus( indentLevel+1, 'Type             : $%02x' % self.type )
                self._printer.printStatus( indentLevel+1, 'Pad Word         : $%04x' % self.padWord )
                self._printer.printStatus( indentLevel+1, 'Destination Addr : $%04x' % self.destAddress )
                self._printer.printStatus( indentLevel+1, 'Length in Chunks : $%04x (%d)' % (self.lengthChunks, self.lengthChunks) )
                self._printer.printStatus( indentLevel+1, 'Poke Address     : $%04x' % self.pokeAddress )
            else:
                if self.index == 0:
                    self._printer.printStatus( indentLevel, 'Header legend:  tp pad0 dest #chk poke' )
                self._printer.printStatus(     indentLevel, 'Header block %d: %02x %04x %04x %04x %04x' % \
                                                            ( \
                                                              self.index, \
                                                              self.type, \
                                                              self.padWord, \
                                                              self.destAddress, \
                                                              self.lengthChunks, \
                                                              self.pokeAddress, \
                                                            ) )
                                                      
        def validate(self):
            """
            Validate the stored values
            Note: only the header values are checked, not whether the header values are within range of the entire records byte array.
            """
            if self.padWord != 0:
                self._printer.errorExit( 4, 'Padding word was $%04x instead of 0.' % self.padWord )
            if self.lengthChunks > self.MAX_CHUNKS:
                self._printer.errorExit( 4, 'Length in chunks ($%04x) exceeds max of $%04x.' % (self.lengthChunks, self.MAX_CHUNKS ) )
                
            if self.type == self.TYPE_BULK_COPY:
                if self.destAddress != self.ADDR_NONE and \
                   self.isAddressLowRange( self.destAddress ) == False and \
                   self.isAddressHighRange( self.destAddress ) == False:
                    self._printer.errorExit( 4, 'Destination address was an out-of-range value of $%04x.' % self.destAddress )
                if self.destAddress != self.ADDR_NONE and self.lengthChunks == 0 or \
                   self.destAddress == self.ADDR_NONE and self.lengthChunks != 0:
                    self._printer.errorExit( 4, 'One of destination address ($%04x) or length in chunks ($04x) was zero when the other was not.' % (self.destAddress, self.lengthChunks) )
                if self.pokeAddress != self.ADDR_NONE and \
                   self.isAddressLowRange( self.pokeAddress ) == False and \
                   self.isAddressHighRange( self.pokeAddress ) == False:
                    self._printer.errorExit( 4, 'Poke address was an out-of-range value of $%04x.' % self.pokeAddress )
            elif self.type == self.TYPE_SKIP_DATA:
                if self.destAddress != self.ADDR_NONE:
                    self._printer.errorExit( 4, 'Destination address was a non-zero value of $%04x in a "skip data" record block.' % self.destAddress )
                if self.lengthChunks == 0:
                    self._printer.errorExit( 4, 'Length in chunks was 0 in "skip data" record block.' )
                if self.pokeAddress != self.ADDR_NONE and \
                   self.isAddressLowRange( self.pokeAddress ) == False and \
                   self.isAddressHighRange( self.pokeAddress ) == False:
                    self._printer.errorExit( 4, 'Poke address was an out-of-range value of $%04x in a "skip data" record block.' % self.pokeAddress )
            else:
                self._printer.errorExit( 4, 'Header block type of $%02x is not recognized.' % self.type )
                
        def isAddressLowRange(self, address):
            """
            Returns boolean for whether the address is in the legal low address range.
            """
            return True if ( address >= self.LOW_ADDR_MIN and address <= self.LOW_ADDR_MAX) else False
        
        def isAddressHighRange(self, address):
            """
            Returns boolean for whether the address is in the legal high address range.
            """
            return True if ( address >= self.HIGH_ADDR_MIN and address <= self.HIGH_ADDR_MAX) else False
            
        def makeAddressHighRange( self, address ):
            return address if address >= self.HIGH_ADDR_MIN else address
