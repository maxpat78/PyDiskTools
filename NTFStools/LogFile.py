# -*- coding: mbcs -*-
from NTFStools.Commons import *

class RestartAreaHeader(object):
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('sMagic', '4s'),
	0x04: ('wUSAOffset', '<H'),
	0x06: ('wUSASize', '<H'),
	0x08: ('u64chkdLSN', '<Q'),
	0x10: ('dwSysPageSize', '<I'),
	0x14: ('dwLogPageSize', '<I'),
	0x18: ('wRestartAreaOffset', '<H'),
	0x1A: ('wMinVer', '<H'),
	0x1C: ('wMajVer', '<H') } # Size = 0x1E (30 byte)
	
	def __init__ (self, diskstream):
		self._i = 0
		self._pos = diskstream.tell() # posizione iniziale
		self._buf = diskstream.read(4096) # dimensione standard del settore di avvio
		if len(self._buf) != 4096:
			raise EndOfStream
		self._kv = RestartAreaHeader.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		
		self.fixup()

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "$LogFile Restart Area Header @%x\n" % self._pos)

	fixup = common_fixup
	
	#~ def fixup(self):
		#~ "Verifica e applica il fixup"
		#~ # la WORD di fixup è all'inizio dell'Update Sequence Array (di WORD)
		#~ fixupn = self._buf[self.wUSAOffset:self.wUSAOffset+2]
		#~ for i in range(1, self.wUSASize):
			#~ fixuppos = i*512 - 2 # ultima WORD del settore
			#~ if fixupn != self._buf[fixuppos:fixuppos+2]:
				#~ print "Fixup della Restart Area errato!"
			#~ offs = self.wUSAOffset+2*i # offset della WORD da sostituire nello USA
			#~ self._buf[fixuppos:fixuppos+2] = self._buf[offs:offs+2]


class RestartArea(object):
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('u64LastLSN', '<Q'),
	0x08: ('wLogClients', '<H'),
	0x0A: ('wClientFreeList', '<H'),
	0x0C: ('wClientInUseList', '<H'),
	0x0E: ('wFlags', '<H'),
	0x10: ('dwSeqNumberBits', '<I'),
	0x14: ('wRestartAreaLength', '<H'),
	0x16: ('wClientArrayOffset', '<H'),
	0x18: ('u64LogFileSize', '<Q'),
	0x20: ('dwLastLSNDataLength', '<I'),
	0x24: ('wLogRecordHeaderLength', '<H'),
	0x26: ('wLogPageDataOffset', '<H'),
	0x28: ('dwRestartLogOpenCount', '<I'),
	0x2C: ('sReserved', '4s') } # Size = 0x30 (48 byte)
	
	def __init__ (self, parent, offset):
		self._i = offset
		self._parent = parent
		#~ self._pos = diskstream.tell() # posizione iniziale
		self._buf = parent._buf
		self._kv = RestartArea.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		
	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "$LogFile Restart Area @%x\n" % self._i)


class LogClientRecord(object):
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('u64OldestLSN', '<Q'),
	0x08: ('u64ClientRestartLSN', '<Q'),
	0x10: ('wPrevClient', '<H'),
	0x12: ('wNextClient', '<H'),
	0x14: ('wSeqNumber', '<H'),
	0x16: ('sReserved', '6s'),
	0x1C: ('dwClientNameLength', '<I'),
	0x20: ('sClientName', '64s') } # Size = 0xA0 (160 byte)
	
	def __init__ (self, parent, offset):
		self._i = offset
		self._parent = parent
		self._buf = parent._buf
		self._kv = LogClientRecord.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		
	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "$LogFile Log Client Record @%x\n" % self._i)


from NTFStools.DiskFile import *

f = DiskFile('$LogFile','rb')
rah = RestartAreaHeader(f)

ra = RestartArea(rah, rah.wRestartAreaOffset)

lcr = LogClientRecord(rah, rah.wRestartAreaOffset + ra.wClientArrayOffset)
print rah, ra, lcr


