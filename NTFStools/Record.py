# -*- coding: mbcs -*-
import array
import logging
import struct
from NTFStools.Attribute import *
from NTFStools.Commons import *

__all__ = ['Record']

class Record(object):
	layout = {
	0x00: ('fileSignature', '4s'),
	0x04: ('wUSAOffset', '<H'), # Update Sequence Array offset
	0x06: ('wUSASize', '<H'), # Array size (in sectors)
	0x08: ('u64LogSeqNumber', '<Q'),
	0x10: ('wSequence', '<H'),
	0x12: ('wHardLinks', '<H'),
	0x14: ('wAttribOffset', '<H'),
	0x16: ('wFlags', '<H'),
	0x18: ('dwRecLength', '<I'),
	0x1C: ('dwAllLength', '<I'),
	0x20: ('u64BaseMftRec', '<Q'),
	0x28: ('wNextAttrID', '<H'),
	0x2A: ('wFixupPattern', '<H'),
	0x2C: ('dwMFTRecNumber', '<I') } # Size = 0x30 (48 byte)
	
	def __init__ (self, mftstream, disk=None):
		self._disk = disk
		self._i = 0 # posizione nel buffer
		self._pos = mftstream.tell() # posizione iniziale
		self._buf = mftstream.read(1024) # dimensione standard del record MFT
		self._stream = mftstream
		self._attributes = {} # dizionario { tipo attributo: [lista esemplari] }
		if len(self._buf) != 1024:
			raise EndOfStream
		self._kv = Record.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
			
		if not self.wFlags & 0x1: # Record non in uso
			return
		
		if self.fileSignature != 'FILE':
			print "Record malformato ma in uso @%x!" % self._pos
			return
		
		self.fixup() # verifica e applica il fixup
		
		# Decodifica gli attributi
		offset = self.wAttribOffset
		while offset < 1024:
			dwType = struct.unpack_from('<I', self._buf, offset)[0]
			if dwType == 0xFFFFFFFF:
				break
			elif dwType == 0x10:
				a = Standard_Information(self, offset)
			elif dwType == 0x20:
				a = Attribute_List(self, offset)
				self._expand_attribute_list(a)
			elif dwType == 0x30:
				a = File_Name(self, offset)
			elif dwType == 0x80:
				a = Data(self, offset)
			elif dwType == 0x90:
				a = Index_Root(self, offset)
			elif dwType == 0xA0:
				a = Index_Allocation(self, offset)
			elif dwType == 0xB0:
				a = Bitmap(self, offset)
			else:
				a = Attribute(self, offset)
			logging.debug("Decodificato attributo:\n%s", a)
			if a.dwType in self._attributes:
				self._attributes[a.dwType] += [a]
			else:
				self._attributes[a.dwType] = [a]
			# Se l'attributo cade oltre un record, qualcosa non va...
			if a.dwFullLength + offset > 1018:
				logging.debug("Attributo oltre il record!!!\n%s", self)
				break
			offset += a.dwFullLength
		logging.debug("Esaminato Record MFT #%x @%x:\n%s", self.dwMFTRecNumber, self._pos, self)

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "MFT Record @%x\n" % self._pos)

	fixup = common_fixup

	#~ def fixup(self):
		#~ "Verifica e applica il fixup del record MFT ai settori componenti"
		#~ # la WORD di fixup è all'inizio dell'Update Sequence Array (di WORD)
		#~ fixupn = self._buf[self.wUSAOffset:self.wUSAOffset+2]
		#~ for i in range(1, self.wUSASize):
			#~ fixuppos = i*512 - 2 # ultima WORD del settore
			#~ if fixupn != self._buf[fixuppos:fixuppos+2]:
				#~ print "Fixup del record MFT errato!"
			#~ offs = self.wUSAOffset+2*i # offset della WORD da sostituire nello USA
			#~ self._buf[fixuppos:fixuppos+2] = self._buf[offs:offs+2]
			
	def next(self, index=1): # BUG! AVANZA anche oltre la fine dello stream!
		"Avanza al prossimo o allo n-esimo record indicato"
		if index > 1:
			self._stream.seek(1024*index)
		else:
			self._stream.seek(self._pos + 1024*index)
		logging.debug("next MFT Record @0x%X, index=%d", self._stream.tell(), index)
		return Record(self._stream, self._disk)
		
	def find_attribute(self, typ):
		if type(typ) == type(''):
			typ = attributes_by_name[typ]
		if typ in self._attributes:
			return self._attributes[typ]
		else:
			return None

	def _expand_attribute_list(self, al):
		i = al._i + 24
		expanded = ()
		while i < al._i + al.dwFullLength:
			dwListedAttrType, wEntryLength, bNameLen,\
			bNameOffs, u64StartVCN, u64BaseMFTFileRef,\
			wAttrID = struct.unpack_from("<IHBBQQH", al._buf, i)
			logging.debug("dwListedAttrType=%s wEntryLength=%s bNameLen=%s bNameOffs=%s u64StartVCN=%s u64BaseMFTFileRef=%s wAttrID=%s", dwListedAttrType, wEntryLength, bNameLen, bNameOffs, u64StartVCN, u64BaseMFTFileRef, wAttrID)
			base = u64BaseMFTFileRef & 0x0000FFFFFFFFFFFF
			if self.dwMFTRecNumber != base and base not in expanded: # attributo in altro record collegato
				rec = Record(self._stream, self._disk)
				rec = rec.next(base)
				self._attributes.update(rec._attributes)
				expanded += (base,)
			i += wEntryLength # avanza al prossimo elemento della lista
