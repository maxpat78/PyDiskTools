PyDiskTools
===========

These Python 2.7 code fragments came from a study around FAT, FAT32, exFAT and NTFS file systems:
the purpose was to help in recovering a corrupted file system, when standard disk utilities can't
help ("RAW disk" error, nuked sector zero, etc.).


NTFStools
=========

The most nice and interesting utility is the ntfscpi.py script in the top level directory: built
on the included NTFStools package, it can directly access a NTFS formatted on-line disk and copy
a file, even if locked by the Windows kernel - no more complicated things with previous file
versions capturing, like the utility HoboCopy does in Vista and newer OSes).

A sample:

	ntfscpi \\.\C: C:\Windows\System32\config\SYSTEM .

to copy a kernel-locked Windows Registry hive file to the current directory (obviously, since it is
an open file, its content could not be consistent because of updating tasks carried out
by other active applications).


FATtools
========

The FATtools are less mature: one has to specify things like FAT position or size by hands, retrieving
them with a good disk hex editor.

However, the FAT32.py helped me in recovering more than 99% of a 4 GiB broken USB key (yes, sometimes
Windows or its USB driver burns the sector zero... and FAT has no backups at the end of the volume, 
like NTFS!).


Final considerations
====================

There is also a PDF article about the above file systems, but it is for Italian people only; comments
in the Python code are, too (sorry, too lazy to translate 19 pages... :D).

Volunteers are welcome to improve code correctness and robustness.

The NTFS $LogFile remains obscure to all of us - even trying to fill it with atomic simple operations
like repeatedly touching a file with the same times gives a too-difficult-to-analyze result.

The DiskFile.py mechanism isn't so good; the caching algorithm (useful only to speed up operations on FAT
chains) should be improved and, hopefully, rethinked.


All the code is licensed under the GPL v2.
