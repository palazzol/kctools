# -*- coding: utf-8 -*-
"""
Created on Tue Dec  6 22:26:17 2016

@author: palazzol
"""

from kcutils import *
import argparse
import sys
import codecs

   

def generatePaddedIndicesString( dimensions, indices, statusPrinter ):
    """
    Generates a string of the indices where each index has the correct amount of padding
        dimensions  - List of integers, each representing the number of elements in that array dimension hasPadByte
        indices     - List of integers, each representing the current index per each array dimension.  The value of
                      indices[i] ranges from 0 to dimensions[i]-1
    Example: a 6 x 5 element array would have dimensions of (6,5) while the current indices could be values from
    (0,0) to (5,4) and the values in-between (2 dimensionally)
    """
    if len(dimensions) != len(indices):
        statusPrinter.errorExit( 1, "The number of dimensions (%d) did not match the number of indices (%d)" % \
                                    ( len(dimensions), len(indices) ))
    
    result = ""
    for i in range( len(dimensions) ):
        dimWidth = 1
        dimension = dimensions[i] - 1
        while dimension > 10:
            dimension /= 10
            dimWidth  += 1
        if i == 0:
            result += "%*d" % (dimWidth, indices[i])
        else:
            result += ",%*d" % (dimWidth, indices[i])
    return result

#
# Set up the command-line options
#
parser = argparse.ArgumentParser(description='Detokenizes KC records or BIN+CFG files into BASIC programs and variables.')
parser.add_argument('-n','--start-record-number', type=int, default=1, help='The record number of the file to start detokenizing.  Default value is 1, thus the default first file is record_0001.bin')
parser.add_argument('-o','--outfile', type=argparse.FileType('w'), default=sys.stdout, help='Output BASIC program file.  Default is to print to the screen.')
parser.add_argument('-v','--varfile', type=argparse.FileType('w', encoding='utf-8'), default=sys.stdout, help='Output BASIC variables file.  Default is to print to the screen.')
parser.add_argument('-p','--print-progress', action='store_true', help='Print progress to the screen.  Useful for multi-record BASIC programs.')
parser.add_argument('-w','--writable-track', action='store_true', help='Parses BASIC from records decoded off of the writable track of a KC tape.  Default is to parse records decoded off of the read-only track.')
parser.add_argument('-s','--spaces-as-kc-list', action='store_true', help='Generates BASIC code the same way the KC\'s LIST command would; without spaces.  Default is to includes spaces for readability.')
parser.add_argument('-f','--rec-files', help='The input path and file names to open.  This is a printf-style string that is expected to accept 0 or 1 integer values.  If the string accepts NO integer values, then the string is EXACT path and name for a single file.  If it accepts ONE integer value, such as a string that contain "%%d" or "%%x", then the formatted values from --rec-start to --rec-end are substituted into the string.  By default, the string "record_%%04d.bin" is used (which results in record_0001.bin, record_0002.bin, record_0003.bin, etc).  ')
parser.add_argument('-b','--in-bin-cfg', help='Input *.bin and *.cfg file pair that contains pre-existing memory mapped data.  Only a single path and filename is needed; the ".bin" and ".cfg" will be appended if needed.  This option disables the default behavior of reading record.bin files, but does not disable explict use of the -f option for reading record.bin files.')
parser.add_argument('-c','--program-string-offset', type=int, default=0, help='BASIC variables are stored to tape separately from BASIC programs.  A program can be updated and move the location of the strings inside of the code without the independently stored variables being updated, causing wrong addresses to be used for program strings.  Use this option to set a positive or negative number to shift the address of program strings during detokenizing.  This option does not affect other types of strings.')
parser.add_argument('-u','--user-display-format', choices=['ascii', 'ansi', 'win-console', 'braille', 'unicode'], help='Enables displaying strings in a user readable format in addition to KC BASIC format.  A format must be specified due to the KC\'s non-standard character set and due to Unicode / font limitations.  Characters not allowed for the specified format or escape sequences that are not recognized are displayed as a decimal number between two ^ characters (ex: ^17^).  Escape sequences that execute actions are described between two ^ characters (ex: setting the left margin to 5 results in ^LMARGIN(5)^).  ascii will convert only the KC characters that are in the displayable ASCII range.  ansi adds support for ISO 8895-1 characters (i.e. Unicode < 0x100).  win-console adds Windows-1252 + IBM CP437 characters, such as box-drawing characters (i.e. Unicode 0x25xx, 0x201E, and 0x219x).  braille adds braille Unicode 0x2800-0x283F and 0x2588.  unicode converts all characters by adding Unicode\'s "Symbols for Legacy Computing" range 1FB00-1FB1D, though support for this range is uncommon.')
args = parser.parse_args()

sys.stdout.reconfigure(encoding='utf-8')
if sys.stdout != args.varfile:
    args.varfile.write( '\ufeff' )  # codecs.BOM_UTF8

tokenSeparator = " "
if args.spaces_as_kc_list:
    tokenSeparator = ""

#
# Read the input files
#
statusPrinter = KCStatusPrinter( args.print_progress )
memoryMap = MCMemoryMap( False, statusPrinter )
wereFilesRead = False
if args.in_bin_cfg != None:
    wereFilesRead = True
    binCfgReader = BinCfgFilePair( args.in_bin_cfg, memoryMap, False, statusPrinter )
    binCfgReader.readFiles()
if args.rec_files != None or wereFilesRead == False:
    basicRecordReader = KCBasicRecordReader( memoryMap, not args.writable_track, args.rec_files, args.start_record_number, -1, statusPrinter )
    basicRecordReader.parse()

#
# Parse the BASIC program
#
statusPrinter.printStatus(0, "Parsing BASIC program...")
blockInfo = KCBasicRecordReader.getBlockInfo( memoryMap, KCBasicRecordReader.BLOCK_TYPE_PROGRAM )
if blockInfo == None or blockInfo.address == 0x0000 or blockInfo.length == 0 or \
   memoryMap.checkStateRange( blockInfo.address, blockInfo.length, MCMemoryMap.STATE_WRITTEN, True ) == False:
    statusPrinter.printStatus(1, "None found.")
else:
    tokens = ['END','FOR','NEXT','DATA','INPUT','DIM','READ','LET','GOTO',
              'RUN','IF','RESTORE','GOSUB','RETURN','REM','STOP','ON','PLOD','PSAV',
              'VLOD','VSAV','DEF','SLOD','PRINT','CONT','LIST','CLEAR','PRT',
              'NEW','TAB(','TO','FN','SPC(','THEN','NOT','STEP','+','-','*','/',
              '#','AND','OR','>','=','<','SGN','INT','ABS','VER','FRE','POS',
              'SQR','RND','LOG','EXP','COS','SIN','TAN','ATN','GETC','LEN',
              'STR$','VAL','ASC','CHR$','LEFT$','RIGHT$','MID$','GO']

    stream = MemoryStreamReader( memoryMap, blockInfo.address, blockInfo.length, statusPrinter )
    offset = stream.read16()

    while offset != 0x0000:
        line = stream.read16()
        args.outfile.write('%d ' % line )
        b = stream.read8()
        startOfLine = 1
        while b != 0:
            if b>127:
                if startOfLine != 1:
                    args.outfile.write( tokenSeparator )
                args.outfile.write('%s%s' % ( tokens[b-128], tokenSeparator ) )
            else:
                args.outfile.write(chr(b))
            b = stream.read8()
            startOfLine = 0
        args.outfile.write("\n")
        offset = stream.read16()
    pass
    
# Parse dynamic strings
# Future option: report garbage/abandoned strings still left in the dynamic strings region.
dynamicStringsBlockInfo = KCBasicRecordReader.getBlockInfo( memoryMap, KCBasicRecordReader.BLOCK_TYPE_DYNA_STRINGS )

#
# Parse scalar variables
#
statusPrinter.printStatus(0, "Parsing BASIC scalars...")
blockInfo = KCBasicRecordReader.getBlockInfo( memoryMap, KCBasicRecordReader.BLOCK_TYPE_SCALARS )
if blockInfo == None or blockInfo.address == 0x0000 or blockInfo.length == 0 or \
   memoryMap.checkStateRange( blockInfo.address, blockInfo.length, MCMemoryMap.STATE_WRITTEN, True ) == False:
    statusPrinter.printStatus(1, "None found.")
else:
    stream = MemoryStreamReader( memoryMap, blockInfo.address, blockInfo.length, statusPrinter )
    
    while stream.getRemainingLength() > 0:
        variable = KCBasicUtils.generateVarName( stream, statusPrinter )
        if variable.isString:
            originalIndex = stream.index
            valueObj = KCBasicUtils.parseString( stream, True, dynamicStringsBlockInfo, args.program_string_offset, \
                                                 'kcbasic', statusPrinter )
            typeString = "Dynamic string" if valueObj.isDynamic else "Program string"
            args.varfile.write( "%-3s = %-50s : REM %s\n" % (variable.name, valueObj.value, typeString ) )
            if valueObj.value.find('CHR$(') >= 0 and args.user_display_format != None:
                stream.setIndex( originalIndex )
                valueObj = KCBasicUtils.parseString( stream, True, dynamicStringsBlockInfo, args.program_string_offset, \
                                                     args.user_display_format, statusPrinter )
                args.varfile.write( "    %s = %s\n" % ( args.user_display_format, valueObj.value ) )
        else:
            value = KCBasicUtils.parseNumber( stream, statusPrinter )
            args.varfile.write( "%-3s = %.8G\n" % (variable.name, value) )
#
# Parse array variables
#
statusPrinter.printStatus(0, "Parsing BASIC arrays...")
blockInfo = KCBasicRecordReader.getBlockInfo( memoryMap, KCBasicRecordReader.BLOCK_TYPE_ARRAYS )
if blockInfo == None or blockInfo.address == 0x0000 or blockInfo.length == 0 or \
   memoryMap.checkStateRange( blockInfo.address, blockInfo.length, MCMemoryMap.STATE_WRITTEN, True ) == False:
    statusPrinter.printStatus(1, "None found.")
else:
    stream = MemoryStreamReader( memoryMap, blockInfo.address, blockInfo.length, statusPrinter )
    while stream.getRemainingLength() > 0:
        variable        = KCBasicUtils.generateVarName( stream, statusPrinter )
        totalLength     = stream.read16()
        numDimensions   = stream.read8()
        if numDimensions <= 0:
            statusPrinter.errorExit( 1, "Array has illegal number of dimensions (%d)" % numDimensions )
            
        totalElements = 1
        dimensions      = []
        for i in range(numDimensions):
            dimensions.append( stream.read16BE() )
            totalElements *= dimensions[i]
            if dimensions[i] <= 0:
                statusPrinter.errorExit( 1, "Array has illegal dimension value.  The %dth dimension was %i." % ( i, dimensions[i] ) )

        args.varfile.write( "%-3s array length %d words, dimensions of %s\n" % (variable.name, totalLength, str(dimensions) ) )

        # Compare the lengths
        # 2 for variable, 2 for totalLength, 1 numDimensions, 2*numDimensions for the dimensions
        computedLength = 2 + 2 + 1 + 2*numDimensions
        if variable.isString:
            computedLength += 3*totalElements   # Each string is 3 long
        else:
            computedLength += 4*totalElements   # Each number is 4 long
        if computedLength != totalLength:
            statusPrinter.errorExit( 1, "Array has mis-matched lengths.  It claims it is %d words but computers to %d words." % \
                                        ( totalLength, computedLength ) )

        # Start with array indices [0,0,0,...,0], using KB BASIC array notation
        indices = []
        for i in range(numDimensions):
            indices.append(0)
        
        # Finally walk the array's data
        for i in range(totalElements):
            if variable.isString:
                originalIndex = stream.index
                valueObj = KCBasicUtils.parseString( stream, False, dynamicStringsBlockInfo, args.program_string_offset, \
                                                     'kcbasic', statusPrinter )
                typeString = "Dynamic string" if valueObj.isDynamic else "Program string"
                args.varfile.write( "    %-3s[%s] = %-50s : REM %s\n" % \
                                            ( variable.name, generatePaddedIndicesString( dimensions, indices, statusPrinter ), \
                                              valueObj.value, typeString ) )
                if valueObj.value.find('CHR$(') >= 0 and args.user_display_format != None:
                    stream.setIndex( originalIndex )
                    valueObj = KCBasicUtils.parseString( stream, False, dynamicStringsBlockInfo, args.program_string_offset, \
                                                         args.user_display_format, statusPrinter )
                    args.varfile.write( "        %s = %s\n" % ( args.user_display_format, valueObj.value ) )
            else:
                value = KCBasicUtils.parseNumber( stream, statusPrinter )
                args.varfile.write( "    %-3s[%s] = %.8G\n" % ( variable.name, \
                                            generatePaddedIndicesString( dimensions, indices, statusPrinter ), value) )
            # The below code is correct.  BASIC multi-dimensional arrays are stored in order such that the 1st dimension
            # is incremented 1st, not the last.  This is the reverse of how C lays its arrays out in memory.
            # Thus, if AR is a 2D array, then memory is laid out such that AR(0,0) is followed by AR(1,0) and NOT by AR(0,1)
            for j in range(numDimensions):
                indices[j] = indices[j] + 1
                if indices[j] < dimensions[j] :
                    break
                indices[j] = 0

#
# Exit successfully
#
if args.print_progress:
    print("Done")
