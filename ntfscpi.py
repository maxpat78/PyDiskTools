# -*- coding: mbcs -*-

"""Sample script showing how to use NTFStools to directly access a file in a NTFS filesystem.

Executed in a Windows command prompt with Administrator privileges, it can access and copy
even files locked or protected by the operating system, since it parses the raw disk structures.

Example syntax:

	ntfscpi \\.\C: C:\Windows\System32\config\SYSTEM .

Open disk C: for direct access and copies in the current directory the SYSTEM registry hive
(tipically locked by the NT kernel)."""

import os.path
import sys
from NTFStools import *

def say(s): print s.encode('cp850')

class myDiskFile(DiskFile):
		def __init__ (self, name, mode='rb', buffering=0, size=0, offset=0):
			self.relative_offset = offset
			DiskFile.__init__(self, name, mode, buffering, size)
			
		def seek(self, offset, whence=0):
			offset += self.relative_offset
			DiskFile.seek(self, offset, whence)
			
if len(sys.argv) < 2:
	say( """Copy a file from a NTFS filesystem directly accessing it.

NTFSCPI <filesystem> <source> <destination>

  <filesystem> is a disk (i.e. \\\\.\\C:) or disk image
  <source> is an absolute pathname to the file to copy
  <destination> is the target directory for the copied file

It can operate on the Windows system disk, if launched with Administrator privileges.

Sample: ntfscpi \\\\.\\C: C:\\Windows\\System32\\config\\SYSTEM .""")
	sys.exit(1)

try:
	disk = myDiskFile(sys.argv[1], 'rb')
except:
	disk = None
	
if not disk:
	say( "Can't open '%s' for direct disk access." % sys.argv[1])
	sys.exit(1)

boot = Bootsector(disk)
# Posizione della $MFT relativa all'inizio del boot sector (=LCN * cluster size)
mftstart = boot.u64MFTLogicalClustNum * boot.wBytesPerSec * boot.uchSecPerClust
disk.seek(mftstart)

print "$MFT retrieved @", hex(mftstart)
mft = Record(disk, disk)

if mft.find_attribute("$FILE_NAME")[0].FileName == '$MFT':
	mft = Record(mft.find_attribute(0x80)[0].file, disk)
else:
	say( "The NTFS Master File Table $MFT was not found!")
	sys.exit(1)

record = ntfs_open_file(sys.argv[2], mft._stream, disk)
if not record:
	say('Source file "%s" not found!' % sys.argv[1])
	sys.exit(1)

head, src = os.path.split(sys.argv[2])
head, dst = os.path.split(sys.argv[3])

if dst == '.' or dst == '..':
	dst += '/'+src

if dst[1] == ':' and len(dst) == 2:
	dst += src
	
ntfs_copy_file(record, dst)

say('Successfully copied "%s" to "%s"' % (src, dst))
