# -*- coding: mbcs -*-
import array
import logging
import StringIO
import struct
from Commons import *
from DatarunStream import *

__all__ = ['Attribute', 'Standard_Information', 'Attribute_List', 'File_Name', 'Data',
'Index_Root', 'Index_Allocation', 'Bitmap', 'attributes_by_id', 'attributes_by_name']


attributes_by_id ={
0x10: "$STANDARD_INFORMATION",
0x20: "$ATTRIBUTE_LIST",
0x30: "$FILE_NAME",
0x80: "$DATA",
0x90: "$INDEX_ROOT",
0xA0: "$INDEX_ALLOCATION",
0xB0: "$BITMAP"
}

attributes_by_name = {}
for id, name in attributes_by_id.items(): attributes_by_name[name] = id

class Attribute(object):
	layout = {
	0x00: ('dwType', '<I'),
	0x04: ('dwFullLength', '<I'),
	0x08: ('uchNonResFlag', 'B'),
	0x09: ('uchNameLength', 'B'),
	0x0A: ('wNameOffset', '<H'),
	0x0C: ('wFlags', '<H'),
	0x0E: ('wInstanceID', '<H') } # intestazione standard di attributo: 0x10 (16) byte
	
	layout_resident = { # layout aggiuntivo per contenuto residente 
	0x10: ('dwLength', '<I'),
	0x14: ('wAttrOffset', '<H'),
	0x16: ('uchFlags', 'B'),
	0x17: ('uchPadding', 'B') } # Size = 0x18 (24) byte totali

	layout_nonresident = { # layout aggiuntivo per contenuto non residente 
	0x10: ('u64StartVCN', '<Q'),
	0x18: ('u64EndVCN', '<Q'),
	0x20: ('wDatarunOffset', '<H'),
	0x22: ('wCompressionSize', '<H'), 
	0x24: ('uchPadding', '4s'),
	0x28: ('u64AllocSize', '<Q'),
	0x30: ('u64RealSize', '<Q'),
	0x38: ('u64StreamSize', '<Q') } # Size = 0x40 (64) byte totali
	
	def __init__(self, parent, offset):
		self._parent = parent # classe Record contenente
		self._buf = parent._buf
		self._i = offset # posizione iniziale
		self._kv = Attribute.layout.copy()
		self._vk = {}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		if self.uchNonResFlag:
			upd = Attribute.layout_nonresident
		else:
			upd = Attribute.layout_resident
		self._kv.update(upd)
		for k, v in upd.items():
			self._vk[v[0]] = k

	__getattr__ = common_getattr

	def __str__ (self):
		return class2str(self, "Attributo @%x\n" % self._i)


class Standard_Information(Attribute):
	# Sempre residente
	specific_layout = {
	0x00: ('u64CTime', '<Q'),
	0x08: ('u64ATime', '<Q'),
	0x10: ('u64MTime', '<Q'),
	0x18: ('u64RTime', '<Q'), 
	0x20: ('dwDOSperm', '<I'),
	0x24: ('dwMaxVerNum', '<I'),
	0x28: ('dwVerNum', '<I'),
	0x2C: ('dwClassId', '<I'),
	0x30: ('dwOwnerId', '<I'),  # Gli ultimi 4 solo da NTFS 3.0 in poi (Windows 2000)
	0x34: ('dwSecurityId', '<I'),
	0x38: ('u64QuotaCharged', '<Q'),
	0x40: ('u64USN', '<Q') } # 0x48 (72) byte per la specifica

	def __init__(self, parent, offset):
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)

	__getattr__ = common_getattr

	def __str__ (self):
		s = ''
		L1 = class2str(self, "$STANDARD_INFORMATION @%x\n" % self._i).split('\n')
		L2 = []
		for key in (0x18, 0x20, 0x28, 0x30):
			o = self._kv[key][0]
			v = getattr(self, o)
			v = nt2uxtime(v)
			L2 += ['%x: %s = %s' % (key, o, v)]
		L1[12:16] = L2
		return '\n'.join(L1)


class Attribute_List(Attribute):
	# Sempre residente
	specific_layout = {}

	def __init__(self, parent, offset):
		self._i = offset
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)

	__getattr__ = common_getattr

	def __str__ (self):
		return class2str(self, "$ATTRIBUTE_LIST @%x\n" % self._i)


class File_Name(Attribute):
	specific_layout = {
	0x00: ('u64FileReference', '<Q'),
	0x08: ('u64CTime', '<Q'),
	0x10: ('u64ATime', '<Q'),
	0x18: ('u64MTime', '<Q'), 
	0x20: ('u64RTime', '<Q'),
	0x28: ('u64AllocatedSize', '<Q'),
	0x30: ('u64RealSize', '<Q'),
	0x38: ('dwFlags', '<I'),
	0x3C: ('dwEA', '<I'),  # Gli ultimi 4 solo da NTFS 3.0 in poi (Windows 2000)
	0x40: ('ucbFileName', 'B'),
	0x41: ('uFileNameNamespace', 'B') } # 0x42 (66) byte per la specifica

	def __init__(self, parent, offset):
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)
		# Sempre residente: quindi, il nome si trova a (24+66) byte dal principio
		i = self._i+90
		self.FileName = ('\xFF\xFE' + self._buf[i:i+self.ucbFileName*2].tostring()).decode('utf16')

	__getattr__ = common_getattr

	def __str__ (self):
		s = ''
		L1 = class2str(self, "$FILE_NAME @%x\n" % self._i).split('\n')
		L2 = []
		for key in (0x20, 0x28, 0x30, 0x38):
			o = self._kv[key][0]
			v = getattr(self, o)
			v = nt2uxtime(v)
			L2 += ['%x: %s = %s' % (key, o, v)]
		L1[13:17] = L2
		return '\n'.join(L1) + '%x: FileName = %s\n' % (self._i+90, self.FileName)


class Data(Attribute):
	specific_layout = {}
	
	def __init__(self, parent, offset):
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)
		if self.uchNonResFlag:
			self.decode() # differire all'uso effettivo dello stream?
			self.file = DatarunStream(self.dataruns, self.u64RealSize, self._parent._disk)
		else:
			i = self._i + self.wAttrOffset
			self.file = StringIO.StringIO(self._buf[i: i+self.dwLength].tostring())
			logging.debug("resident $DATA @%x", i)
		

	__getattr__ = common_getattr

	def __str__ (self):
		return class2str(self, "$DATA @%x\n" % self._i)

	decode = common_dataruns_decode


class Index_Root(Attribute):
	specific_layout = {
	0x00: ('dwIndexedAttrType', '<I'),
	0x04: ('dwCollation', '<I'),
	0x08: ('dwAllocEntrySize', '<I'),
	0x0C: ('bClusPerIndexRec', 'B'), 
	0x0D: ('sPadding', '3s') } # 0x10 (16) byte per la specifica

	def __init__(self, parent, offset):
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)
		if self.uchNonResFlag:
			self.decode()
			self.file = DatarunStream(self.dataruns, self.u64RealSize, self._parent._disk)
		else:
			#~ i = self._i + 40 + self.uchNameLength*2
			i = self._i + self.wAttrOffset
			self.file = StringIO.StringIO(self._buf[i: i+self.dwLength].tostring())
			logging.debug("resident $INDEX_ROOT @%x", i)

	__getattr__ = common_getattr

	def __str__ (self):
		return class2str(self, "$INDEX_ROOT @%x\n" % self._i)

	decode = common_dataruns_decode


class Index_Allocation(Attribute):
	specific_layout = {}

	def __init__(self, parent, offset):
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)
		if self.uchNonResFlag:
			self.decode()
			self.file = DatarunStream(self.dataruns, self.u64RealSize, self._parent._disk)
		else:
			#~ i = self._i + 24 + self.uchNameLength*2
			i = self._i + self.wAttrOffset
			self.file = StringIO.StringIO(self._buf[i: i+self.dwLength].tostring())
			logging.debug("resident $INDEX_ALLOCATION @%x", i)

	__getattr__ = common_getattr

	def __str__ (self):
		return class2str(self, "$INDEX_ALLOCATION @%x\n" % self._i)

	decode = common_dataruns_decode

"""
Una bitmap è presente, in particolare:
- come attributo del record $MFT, ove indica quali record FILE sono inutilizzati;
- come contenuto di $INDEX_ALLOCATION, ove indica quali blocchi INDX non sono utilizzati;
- come contenuto del record $Bitmap, per segnalare i cluster liberi nel volume.
"""
class Bitmap(Attribute):
	specific_layout = {}

	def __init__(self, parent, offset):
		Attribute.__init__(self, parent, offset)
		common_update_and_swap(self)
		if self.uchNonResFlag:
			self.decode()
			self.file = DatarunStream(self.dataruns, self.u64RealSize, self._parent._disk)
		else:
			#~ i = self._i + 24 + self.uchNameLength*2
			i = self._i + self.wAttrOffset
			self.file = StringIO.StringIO(self._buf[i: i+self.dwLength].tostring())
			logging.debug("resident $BITMAP @%x", i)

	__getattr__ = common_getattr

	def __str__ (self):
		return class2str(self, "$BITMAP @%x\n" % self._i)

	decode = common_dataruns_decode

	def isset(self, bit):
		byte = bit/8
		bit = bit%8
		self.file.seek(byte)
		b = self.file.read(1)
		return ord(b) & (1 << bit) != 0
