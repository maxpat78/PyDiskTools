# -*- coding: mbcs -*-
import array
import logging
import os
import struct
import time
from FAT import *
from NTFStools.Commons import *
from NTFStools.DiskFile import DiskFile

class Boot(object):
	"Settore di avvio exFAT"
	
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('chJumpInstruction', '3s'),
	0x03: ('chOemID', '8s'),
	0x0B: ('chDummy', '53s'),
	0x40: ('u64PartOffset', '<Q'),
	0x48: ('u64VolumeLength', '<Q'),
	0x50: ('dwFATOffset', '<I'), # in settori
	0x54: ('dwFATLength', '<I'),
	0x58: ('dwDataRegionOffset', '<I'), # in settori
	0x5C: ('dwDataRegionLength', '<I'),
	0x60: ('dwRootCluster', '<I'),
	0x64: ('dwVolumeSerial', '<I'),
	0x68: ('wFSRevision', '<H'),
	0x6A: ('wFlags', '<H'),
	0x6C: ('uchBytesPerSector', 'B'), # esponente di 2
	0x6D: ('uchSectorsPerCluster', 'B'), # esponente di 2
	0x6E: ('uchFATCopies', 'B'),
	0x6F: ('uchDriveSelect', 'B'),
	0x70: ('uchPercentInUse', 'B'),
	0x71: ('chReserved', '7s'),
	0x72: ('chBootstrapCode', '390s'),
	0x1FE: ('wBootSignature', '<H') } # Size = 0x100 (512 byte)
	
	def __init__ (self, diskstream, offset=0):
		self._i = 0
		self._pos = diskstream.tell() # posizione iniziale
		self._buf = diskstream.read(512) # dimensione standard del settore di avvio
		self.stream = diskstream
		if len(self._buf) != 512:
			raise EndOfStream
		self._kv = self.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		# Dimensione del cluster in byte
		self.cluster = (1 << self.uchBytesPerSector) * (1 << self.uchSectorsPerCluster)
		# Offset della prima FAT
		self.fatoffs = self.dwFATOffset * (1 << self.uchBytesPerSector) + self._pos
		# Numero di slot (=cluster) della FAT
		self.fatsize = self.dwDataRegionLength
		# Offset dell'area dati (=cluster #2)
		self.dataoffs = self.dwDataRegionOffset * (1 << self.uchBytesPerSector) + self._pos

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "Settore di avvio exFAT @%x\n" % self._pos)

	def cl2offset(self, cluster):
		"Calcola l'offset effettivo di un cluster"
		return self.dataoffs + (cluster-2)*self.cluster

	def root(self):
		"Offset della root directory"
		return self.cl2offset(self.dwRootCluster)


class DirEntry(object):
	"Voce di tabella di directory exFAT"
	
	volume_label_layout = { # 0x83, 0x03
	0x00: ('chEntryType', 'B'),
	0x01: ('chCount', 'B'),
	0x02: ('sVolumeLabel', '22s'),
	0x18: ('sReserved', '8s') }

	bitmap_layout = { # 0x81
	0x00: ('chEntryType', 'B'),
	0x01: ('chFlags', 'B'),
	0x02: ('sReserved', '18s'),
	0x14: ('dwStartCluster', '<I'),
	0x18: ('u64BitmapLength', '<Q')	}

	upcase_layout = { # 0x82
	0x00: ('chEntryType', 'B'),
	0x01: ('sReserved1', '3s'),
	0x04: ('dwChecksum', '<I'),
	0x08: ('sReserved2', '12s'),
	0x14: ('dwStartCluster', '<I'),
	0x18: ('u64DataLength', '<Q')	}

	volume_guid_layout = { # 0xA0, 0x20?
	0x00: ('chEntryType', 'B'),
	0x01: ('chSecondaryCount', 'B'),
	0x02: ('wChecksum', '<H'),
	0x04: ('wFlags', '<H'),
	0x06: ('sVolumeGUID', '16s'),
	0x16: ('sReserved', '10s') }

	texfat_padding_layout = { # 0xA1
	0x00: ('sReserved', '31s') }

	file_entry_layout = { # 0x85, 0x05
	0x00: ('chEntryType', 'B'),
	0x01: ('chSecondaryCount', 'B'),
	0x02: ('wChecksum', '<H'),
	0x04: ('wFileAttributes', '<H'),
	0x06: ('sReserved2', '2s'),
	0x08: ('dwCTime', '<I'),
	0x0C: ('dwMTime', '<I'),
	0x10: ('dwATime', '<I'),
	0x14: ('chmsCTime', 'B'),
	0x15: ('chmsMTime', 'B'),
	0x16: ('chtzCTime', 'B'),
	0x17: ('chtzMTime', 'B'),
	0x18: ('chtzATime', 'B'),
	0x19: ('sReserved2', '7s') }

	stream_extension_layout = { # 0xC0, 0x40
	0x00: ('chEntryType', 'B'),
	0x01: ('chSecondaryFlags', 'B'),
	0x02: ('sReserved1', 's'),
	0x03: ('chNameLength', 'B'),
	0x04: ('wNameHash', '<H'),
	0x06: ('sReserved2', '2s'),
	0x08: ('u64ValidDataLength', '<Q'),
	0x10: ('sReserved3', '4s'),
	0x14: ('dwStartCluster', '<I'),
	0x18: ('u64DataLength', '<Q') }

	file_name_extension_layout = { # 0xC1, 0x41
	0x00: ('chEntryType', 'B'),
	0x01: ('chSecondaryFlags', 'B'),
	0x02: ('sFileName', '30s') }

	slot_types = {
	0x00: ({0x00: ('sRAW','32s')}, "Sconosciuto"),
	0x01: (bitmap_layout, "Allocation Bitmap"),
	0x02: (upcase_layout, "Upcase Table"),
	0x03: (volume_label_layout, "Volume Label"),
	0x05: (file_entry_layout, "File Entry"),
	0x20: (volume_guid_layout, "Volume GUID"),
	0x21: (texfat_padding_layout, "T-exFAT padding"),
	0x40: (stream_extension_layout, "Stream Extension"),
	0x41: (file_name_extension_layout, "Filename Extension") }
	
	def __init__ (self, stream):
		self._i = 0
		self._pos = stream.tell() # posizione iniziale
		self._buf = stream.read(32) # dimensione standard dello slot
		self.stream = stream
		self.unused = 0
		self.deleted = 0
		if len(self._buf) != 32:
			raise EndOfStream
		typ = ord(self._buf[0])
		if not typ & 0x80:
			self.deleted = 1
		typ &= 0x7F
		if typ == 0 or typ not in self.slot_types:
			self.unused = 1
			typ = 0
			logging.warning("Tipo di slot sconosciuto: %x", typ)
		self._kv = self.slot_types[typ][0].copy() # seleziona il tipo di slot appropriato
		self._name = self.slot_types[typ][1]
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		logging.debug("Decodificata %s", self)

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "%s @%x\n" % (self._name, self._pos))
		

class Slot(object):
	"Assembla 3 o più slot di file (directory) exFAT"
	def __init__ (self, slots, root):
		fe = slots.pop(0) # main file entry
		if fe.chSecondaryCount != len(slots):
			logging.warning("chSecondaryCount (%d) != len(slots) (%d)", fe.chSecondaryCount, len(slots))
			return None
		se = slots.pop(0) # stream ext
		name = ''
		for ne in slots:
			name += ne.sFileName
		name = name[:se.chNameLength*2]
		self.Name = ('\xFF\xFE' + name).decode('utf16')
		self.IsDirectory = bool(fe.wFileAttributes & 0x10)
		self.IsDeleted = fe.deleted
		self.NoFAT = bool(se.chSecondaryFlags & 0x2) # bit 1 set == no FAT chain
		self.Parent = root
		self.Size = se.u64DataLength
		self.Start= se.dwStartCluster
		# Aggiungere i 1/100 di secondo e la TZ?
		self.CTime = time.mktime(self.datetimeparse(fe.dwCTime))
		self.MTime = time.mktime(self.datetimeparse(fe.dwMTime))
		self.ATime = time.mktime(self.datetimeparse(fe.dwATime))

	def datetimeparse(self, dwDatetime):
		"Decodifica 2 WORD di data e ora DOS in tuple"
		wDate = (dwDatetime & 0xFFFF0000) >> 16
		wTime = (dwDatetime & 0x0000FFFF)
		return (wDate>>9)+1980, (wDate>>5)&0xF, wDate&0x1F, wTime>>11, (wTime>>5)&0x3F, wTime&0x1F, 0, 0, 0


def fat_recover_slot(boot, fat, slot, destdir=''):
	"Recupera un file da uno slot di directory già decodificato"
	if slot.IsDirectory:
		return
	if not os.path.exists(os.path.join(destdir,slot.Parent)):
		try:
			os.makedirs(os.path.join(destdir,slot.Parent))
		except:
			pass
	# Apre la catena sorgente come file
	chain = Chain(boot, fat, slot.Start, size=slot.Size, nofat=slot.NoFAT)
	dest = os.path.join(destdir, slot.Parent, slot.Name)
	out = open(dest, 'wb')
	buf = 1
	while buf:
		buf = chain.read(boot.cluster)
		out.write(buf)
	out.truncate(slot.Size)
	out.close()
	os.utime(dest, (slot.ATime, slot.MTime))
	#~ print "Recuperato %s (%d byte, cluster %d)." % (slot.Name, slot.Size, slot.Start)
	logging.info("Recuperato %s (%d byte, cluster %d).", slot.Name, slot.Size, slot.Start)

def fat_traverse_tree(boot, fat, startcluster, root='.', test=None, action=None, nofat=0):
	"Decodifica una tabella di directory ed esegue un'azione se passa un test (o questo manca)."

	logging.info("Ingresso nella directory %s", root)
	
	def decode_slots(slots):
		slot = Slot(slots, root)
		if not test or test(slot):
			if slot.IsDirectory: # subordinare al test anche la discesa nelle directory?
				folder = os.path.join(root,slot.Name)
				nofat = 0
				if slot.NoFAT: nofat = slot.Size
				fat_traverse_tree(boot, fat, slot.Start, folder, test, nofat=nofat, action=action)
			else:
				action(boot, fat, slot)
			s = ("file", "directory")[slot.IsDirectory]
			logging.info("Individuato %s (%s; %d byte, cluster %d).", slot.Name.decode('mbcs'), s, slot.Size, slot.Start)
		
	chain = Chain(boot, fat, startcluster, size=nofat, nofat=nofat)
	slots = []
	while 1:
		try:
			entry = DirEntry(chain)
		# decodifica l'ultimo gruppo a fine stream, fine tabella o nuovo oggetto
		except EndOfStream:
			decode_slots(slots)
			break
		if entry.unused: # Unused slot area
			decode_slots(slots)
			logging.warning('Rilevata area di slot non in uso @%x', entry._pos)
			break
		if entry.deleted: # Deleted
			logging.warning('Rilevato slot cancellato @%x', entry._pos)
			continue
		if entry.chEntryType & 0x7F in (0x40, 0x41):
			slots += [entry]
			continue
		if entry.chEntryType & 0x7F == 0x05:
			if slots: # Se abbiamo già raccolto slot per un precedente oggetto...
				decode_slots(slots)
				slots = []
			logging.warning('Rilevato slot di File Name @%x', entry._pos)
			slots += [entry]
			continue
	
	logging.info("Uscita dalla directory %s", root)



if __name__ == '__main__':
	from datetime import datetime
	def list_slot(boot, fat, slot):
		print "%s   %8d %s" % (datetime.fromtimestamp(slot.MTime).isoformat(), slot.Size, os.path.join(slot.Parent, slot.Name))

	def md5_slot(boot, fat, slot, fp):
		import md5
		if not slot.Size or slot.Size > 10**9:
			return
		md = md5.new()
		chain = Chain(boot, fat, slot.Start, size=slot.Size, nofat=slot.NoFAT)
		buf = 1
		while buf:
			buf = chain.read(32*(1<<20))
			md.update(buf)
		fp.write( '%s *G:%s\n' % (md.hexdigest(), os.path.join(slot.Parent,slot.Name)) )
		print "Calcolato MD5 per", slot.Name
		#~ good = md5.new(open(os.path.join("U:",slot.Parent,name),'rb').read()).hexdigest()
		#~ if md.hexdigest() != good:
			#~ print "I checksum MD5 per %s non coincidono!" % name
		#~ else:
			#~ print "Checksum MD5 corretto per", name
		
	action = lambda x, y, z: fat_recover_slot(x, y, z, 'H:')
	
	action = lambda x, y, z: list_slot(x, y, z)
	
	outmd5 = open('checksums.md5','w')
	action = lambda x, y, z: md5_slot(x, y, z, outmd5)

	logging.basicConfig(level=logging.ERROR, filename='exFAT.log', filemode='w')
	
	start = datetime.now()
	
	disk = DiskFile('\\\\.\\G:', 'rb')
	#~ disk = DiskFile(r'C:\Users\Public\exfat32m.img', 'rb')
	boot = Boot(disk)
	fat = FAT(disk, boot.fatoffs, boot.fatsize, exfat=1)
	fat_traverse_tree(boot, fat, boot.dwRootCluster, '.', test=lambda x: 1, action=action)
	disk.cache.print_stats()

	print "Durata dell'esecuzione:", datetime.now() - start