# -*- coding: mbcs -*-
import logging
from NTFStools.Commons import *

class Index(object):
	def __init__ (self, indxstream, bitmap, resident=0):
		self._stream = indxstream
		self._bitmap = bitmap # ce l'ha solo la $INDEX_ALLOCATION
		self._pos = self._stream.tell()
		self._resident = resident
		# La $BITMAP determina quali cluster dell'indice sono liberi
		# I cluster finali liberi possono essere privi di marcatore INDX!
		#~ if not self._bitmap.isset(self._pos/4096):
			#~ self._stream.seek(4096, 1)
		self._buf = self._stream.read(4096)
		if type(self._buf) == type(''):
			self._buf = array.array('c', self._buf)
		if not resident and len(self._buf) < 4096:
			raise EndOfStream
		if resident:
			self._indxh = Index_Header(self._buf)
		else:
			try:
				block = Index_Block(self._buf)
			except BadIndex:
				if self._bitmap and not self._bitmap.isset(self._pos/4096):
					logging.debug("Cluster INDX %d non in uso a zero", self._pos/4096)
					raise EndOfStream
				else:
					raise BadIndex
			logging.debug("decodificato INDEX_BLOCK:\n%s", block)
			self._indxh = Index_Header(self._buf, 24)
		logging.debug("decodificata INDEX_HEADER:\n%s", self._indxh)

	def __str__ (self):
		return class2str(self, "Index @%x\n" % self._pos)

	__getattr__ = common_getattr
		
	def next(self):
		while 1:
			i = self._indxh.dwEntriesOffset
			while i < self._indxh.dwIndexLength:
				e = Index_Entry(self._buf, i+self._indxh._i)
				if e:
					# Una voce con nome vuoto segnala la fine del blocco INDX
					if e.FileName: 
						yield e
					if e.wFlags & 0x2: # Last INDX entry
						logging.debug("LAST INDX ENTRY DETECTED: BREAKING!")
						break
				else:
					raise StopIteration
				i += e.wsizeOfIndexEntry
			if not self._resident:
				# Legge il prossimo blocco INDX
				try:
					self.__init__(self._stream, self._bitmap, self._resident)
				except EndOfStream:
					# Trasforma in eccezione gestita da for ... in
					raise StopIteration

class Index_Block(object):
	layout = {
	0x00: ('sMagic', '4s'),
	0x04: ('wUSAOffset', '<H'), # Update Sequence Array offset
	0x06: ('wUSASize', '<H'), # Array size (in sectors)
	0x08: ('u64LSN', '<Q'),
	0x10: ('u64IndexVCN', '<Q') } # 0x18 (24) byte

	def __init__ (self, indx):
		self._i = 0
		self._buf = indx
		self._kv = Index_Block.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		if self.sMagic != 'INDX':
			raise BadIndex
		self.fixup()

	__getattr__ = common_getattr

	fixup = common_fixup
		
	#~ def fixup(self):
		#~ "Verifica e applica il fixup del record INDX ai settori componenti"
		#~ # la WORD di fixup è all'inizio dell'Update Sequence Array (di WORD)
		#~ fixupn = self._buf[self.wUSAOffset:self.wUSAOffset+2]
		#~ for i in range(1, self.wUSASize):
			#~ fixuppos = i*512 - 2 # ultima WORD del settore
			#~ if fixupn != self._buf[fixuppos:fixuppos+2]:
				#~ print "Fixup del record INDX errato!"
			#~ offs = self.wUSAOffset+2*i # offset della WORD da sostituire nello USA
			#~ self._buf[fixuppos:fixuppos+2] = self._buf[offs:offs+2]

	def __str__ (self):
		return class2str(self, "Index Block @%x\n" % self._i)

class Index_Header(object):
	layout = {
	0x00: ('dwEntriesOffset', '<I'), 
	0x04: ('dwIndexLength', '<I'),
	0x08: ('dwAllocatedSize', '<I'),
	0x0C: ('bIsLeafNode', 'B'),
	0x0D: ('sPadding', '3s') } # Size = 0x10 (16 byte)
	
	def __init__ (self, indx, offset=0):
		self._buf = indx
		self._i = offset
		self._kv = Index_Header.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "Index Header @%x\n" % self._i)

class Index_Entry(object):
	layout = {
	0x00: ('u64mftReference', '<Q'),
	0x08: ('wsizeOfIndexEntry', '<H'),
	0x0A: ('wfilenameOffset', '<H'),
	0x0C: ('wFlags', '<H'),
	0x0E: ('sPadding', '2s'),
	0x10: ('u64mftFileReferenceOfParent', '<Q'),
	0x18: ('u64creationTime', '<Q'),
	0x20: ('u64lastModified', '<Q'),
	0x28: ('u64lastModifiedForFileRecord', '<Q'),
	0x30: ('u64lastAccessTime', '<Q'),
	0x38: ('u64allocatedSizeOfFile', '<Q'),
	0x40: ('u64realFileSize', '<Q'),
	0x48: ('u64fileFlags', '<Q'),
	0x50: ('ucbFileName', 'B'),
	0x51: ('chfilenameNamespace', 'B') } # Size = 0x52 (82 byte)
	
	def __init__ (self, buffer, index):
		self._kv = Index_Entry.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		self._buf = buffer
		self._i = index
		self.FileName = ''
		if self.wfilenameOffset: # Un'ultima voce può essere priva di nome!
			j = index + 82
			self.FileName = ('\xFF\xFE' + self._buf[j: j+self.ucbFileName*2].tostring()).decode('utf16')
		logging.debug('Decodificata INDEX_ENTRY @%x\n%s', index, self)

	__getattr__ = common_getattr
		
	def __str__ (self):
		s = ''
		L1 = class2str(self, "Index Entry @%x\n" % self._i).split('\n')
		L2 = []
		for key in (0x18, 0x20, 0x28, 0x30):
			o = self._kv[key][0]
			v = getattr(self, o)
			v = nt2uxtime(v)
			L2 += ['%x: %s = %s' % (key, o, v)]
		L1[7:11] = L2
		return '\n'.join(L1) + '52: FileName = %s\n' % self.FileName
