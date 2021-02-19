# -*- coding: utf-8 -*-
"""
Handles mapping a variety of input files into an Intellivision memory map.

This program takes the following inputs:
    BIN+CFG file pair
    Record files from Keyboard Component tapes.  The following types are supported:
        Read-Only data
        Read-Only BASIC
        Read-Write BASIC
        
It outputs a BIN+CFG file pair (optional).

By default, it fails if the inputs attempt to overwrite data already in the memory map.

Created: Wed Dec 30 2020
Author: Chris Dreher
"""

from kcutils import *

        
def main():
    """
    Executes main code
    """
    parser = argparse.ArgumentParser(description='Builds memory map from the Master Component\'s perspective.  Main output is BIN+CFG files.')
    parser.add_argument('--in-bin-cfg', help='Input *.bin and *.cfg file pair that contains pre-existing memory mapped data.  Only a single path and filename is needed; the ".bin" and ".cfg" will be appended if needed.  If omitted, then there is no pre-existing memory map data.')
    parser.add_argument('--out-bin-cfg', help='Output *.bin and *.cfg files pair.  On output, these will contain merged data from the input *.bin and *.cfg files and from the records.  Only a single path and filename is needed; the ".bin" and ".cfg" will be appended if needed.  If omitted, then normal processing will be performed but no memory map data will be written.')
    parser.add_argument('--rec-type', choices=['ro_data', 'rw_data', 'ro_basic', 'rw_basic'], default='ro_data', help='Specifies the type of Keyboard Component records being input.')
    parser.add_argument('--rec-start', type=int, default=1, help='Starting Keyboard Component record number.  Default is 1.')
    parser.add_argument('--rec-end', type=int, default=-1, help='Ending Keyboard Component record number.  This is required for rectypes of ro_data and rw_data.  It is optional for rectypes of ro_basic and rw_basic.  For the latter rectypes, record parsing will stop either after parsing the recend record or when the end is auto-detected.')
    parser.add_argument('--rec-files', help='The path and file names to open.  This is a printf-style string that is expected to accept 0 or 1 integer values.  If the string accepts NO integer values, then the string is EXACT path and name for a single file.  If it accepts ONE integer value, such as a string that contain "%%d" or "%%x", then the formatted values from --rec-start to --rec-end are substituted into the string.  By default, the string "record_%%04d.bin" is used (which results in record_0001.bin, record_0002.bin, record_0003.bin, etc).  ')
    parser.add_argument('--rec-truncation-ok', action='store_true', help='By default, if a record is shorter than the header indicates, then this causes an error.  This flag changes the error to only a warning.' )
    parser.add_argument('--mem-overwrite', action='store_true', help='Normally, it is an error when attempting to overwrite data already in the memory with a different value (i.e. not allowed to change existing data).  This flag disables this error.  For example, this flag will allow data from record_0002.bin to overwrite overlapping data already included by record_0001.bin.')
    parser.add_argument('--mem-block-size',type=int, default=1, help='Sets how many bits wide memory blocks will be in the output BIN and CFG file.  A memory block is a memory range that contains at least 1 decle from one of the inputs and enough zeros to pad out the remainder of the block.  A memory block is also aligned to memory addresses that are multiples of its size.  For example, if --mem-boundary-size is 4, and address $1234 had data from one of the input files, then memory blocks will be 16 decles in size and addresses $1230-$123f will be in the output BIN and CFG file.  Legal values range from 1 (addresses are decle aligned) to 16 (the entire address range output).  Note that a value of 8 is compatible with the Cuttle Cart 3.')
    parser.add_argument('--file-overwrite', action='store_true', help='Normally, it is an error when attempting to overwrite an existing file.  This flag disables this error.')
    parser.add_argument('--short-logging', action='store_true', help='Normally, logging is verbose.  This flag enables shorter or less verbose logging.')

    args = parser.parse_args()
    
    printer = KCStatusPrinter( True )
    
    if args.mem_block_size < 1 or args.mem_block_size > 16:
        printer.errorExit( 1, "Illegal --mem-block-size of %d specified.  Only values 1 through 16 are legal" % args.mem_block_size )
    
    memoryMap = MCMemoryMap( args.mem_overwrite, printer )
    
    # Read the input BIN+CFG files
    inBinCfg = None
    if args.in_bin_cfg != None:
        inBinCfg = BinCfgFilePair( args.in_bin_cfg, memoryMap, False, printer )
        inBinCfg.readFiles()
        
    # Read and parse the record files
    if   args.rec_type == 'ro_data':
        recordReader = KCRODataRecordReader( memoryMap, args.rec_files, args.rec_start, args.rec_end, args.rec_truncation_ok, printer, args.short_logging )
        recordReader.parse()
    elif args.rec_type == 'rw_data':
        printer.errorExit( 1, "NOT-YET-IMPLEMENTED --rec-type value of %s" % args.rec_type )
    elif args.rec_type == 'ro_basic':
        recordReader = KCBasicRecordReader( memoryMap, True, args.rec_files, args.rec_start, args.rec_end, printer )
        recordReader.parse()
    elif args.rec_type == 'rw_basic':
        recordReader = KCBasicRecordReader( memoryMap, False, args.rec_files, args.rec_start, args.rec_end, printer )
        recordReader.parse()
    else:
        printer.errorExit( 1, "Illegal --rec-type value of %s" % args.rec_type )
        
    # Set the memory block size
    memoryMap.alignMemoryBlock( args.mem_block_size )
        
    # Write the output BIN+CFG files
    if args.out_bin_cfg != None:
        outBinCfg = BinCfgFilePair( args.out_bin_cfg, memoryMap, args.file_overwrite, printer )
        outBinCfg.appendCfg( inBinCfg )
        outBinCfg.writeFiles()
        
    print( "Done\n" )

# Only execute main() if this script if being directly executed (not imported)
if __name__ == "__main__":
    main()
