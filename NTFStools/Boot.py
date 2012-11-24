# -*- coding: mbcs -*-
from NTFStools.Commons import *

class Bootsector(object):
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('chJumpInstruction', '3s'),
	0x03: ('chOemID', '4s'),
	0x07: ('chDummy', '4s'),
	0x0B: ('wBytesPerSec', '<H'),
	0x0D: ('uchSecPerClust', 'B'),
	0x0E: ('wReservedSec', '<H'),
	0x11: ('uchReserved', '3s'),
	0x14: ('wUnused1', '<H'),
	0x16: ('uchMediaDescriptor', 'B'),
	0x17: ('wUnused2', '<H'),
	0x19: ('wSecPerTrack', '<H'),
	0x1B: ('wNumberOfHeads', '<H'),
	0x1D: ('dwHiddenSec', '<I'),
	0x21: ('dwUnused3', '<I'),
	0x25: ('dwUnused4', '<I'),
	0x29: ('u64TotalSec', '<Q'),
	0x30: ('u64MFTLogicalClustNum', '<Q'),
	0x38: ('u64MFTMirrLogicalClustNum', '<Q'),
	0x40: ('nClustPerMFTRecord', '<I'),
	0x44: ('nClustPerIndexRecord', '<I'),
	0x48: ('u64VolumeSerialNum', '<Q'),
	0x50: ('dwChecksum', '<I'),
	0x54: ('chBootstrapCode', '426s'),
	0x1FE: ('wSecMark', '<H') } # Size = 0x100 (512 byte)
	
	def __init__ (self, diskstream):
		self._i = 0
		self._pos = diskstream.tell() # posizione iniziale
		self._buf = diskstream.read(512) # dimensione standard del settore di avvio
		if len(self._buf) != 512:
			raise EndOfStream
		self._kv = Bootsector.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "Settore di avvio NTFS @%x\n" % self._pos)
		
	def MFTStart(self):
		"""Posizione della Master File Table, MFT. Il record $MFT (e il duplicato $MFTMirr)
		sono presenti anche al principio del secondo cluster del disco."""
		return self.u64MFTLogicalClustNum * self.wBytesPerSec * self.uchSecPerClust
