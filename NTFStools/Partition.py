# -*- coding: mbcs -*-
from Commons import *
from DiskFile import *

"""
La prima partzione di E: si trova a 0x800*512 byte
(=100000h)
La dimensione della partizione è 0x2e938000/2048 = 381552 MiB, in settori da 512 byte)

"""
class Partition(object):
	layout = { # 0x10 (16) byte
	0x00: ('chBootInd', 'B'),
	0x01: ('chHead', 'B'),
	0x02: ('chSector', 'B'),
	0x03: ('chCylinder', 'B'),
	0x04: ('chType', 'B'),
	0x05: ('chLastHead', 'B'),
	0x06: ('chLastSector', 'B'),
	0x07: ('chLastCylinder', 'B'),
	0x08: ('dwRelativeSector', '<I'), # inizio della partizione, in settori
	0x0C: ('dwNumberSectors', '<I') } # dimensione della partizione, in settori
	
	def __init__ (self, diskstream):
		self._i = 0x1BE # offset della Partition Table nel MBR
		self._pos = diskstream.tell() # posizione iniziale
		self._buf = diskstream.read(512) # dimensione standard del Master Boot Record
		if len(self._buf) != 512:
			raise EndOfStream
		if self._buf[-2:].tostring() != '\x55\xAA':
			print "Bad MBR!"
		self._kv = Partition.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "Master Boot Record @%x\n" % self._pos)
		
	def start(self):
		"""Posizione della Master File Table, MFT. Il record $MFT (e il duplicato $MFTMirr)
		sono presenti anche al principio del secondo cluster del disco."""
		return self.u64MFTLogicalClustNum * self.wBytesPerSec * self.uchSecPerClust

disk = DiskFile('\\\\.\\PhysicalDrive2', 'rb')
mbr = Partition(disk)
print mbr