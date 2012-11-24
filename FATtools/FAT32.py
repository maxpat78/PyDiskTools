# -*- coding: mbcs -*-
import logging
import os
import struct
import time
from FAT import *
from NTFStools.Commons import *
from NTFStools.DiskFile import DiskFile


class Boot(object):
	"Settore di avvio FAT32"
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('chJumpInstruction', '3s'),
	0x03: ('chOemID', '8s'),
	0x0B: ('wBytesPerSector', '<H'),
	0x0D: ('uchSectorsPerCluster', 'B'),
	0x0E: ('wSectorsCount', '<H'),
	0x10: ('uchFATCopies', 'B'),
	0x11: ('wMaxRootEntries', '<H'),
	0x13: ('wTotalSectors', '<H'),
	0x15: ('uchMediaDescriptor', 'B'),
	0x16: ('wSectorsPerFAT', '<H'),
	0x18: ('wSectorsPerTrack', '<H'),
	0x1A: ('wHeads', '<H'),
	0x1C: ('wHiddenSectors', '<H'),
	0x1E: ('wTotalHiddenSectors', '<H'),
	0x20: ('dwTotalLogicalSectors', '<I'),
	0x24: ('dwSectorsPerFAT', '<I'),
	0x28: ('wMirroringFlags', '<H'),
	0x2A: ('wVersion', '<H'),
	0x2C: ('dwRootCluster', '<I'),
	0x30: ('wFSISector', '<H'),
	0x32: ('wBootCopySector', '<H'),
	0x34: ('chReserved', '12s'),
	0x40: ('chPhysDriveNumber', 'B'),
	0x41: ('chFlags', 'B'),
	0x42: ('chExtBootSignature', 'B'),
	0x43: ('dwVolumeID', '<I'),
	0x47: ('sVolumeLabel', '11s'),
	0x52: ('sFSType', '8s'),
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
		self.cluster = self.wBytesPerSector * self.uchSectorsPerCluster
		# Offset della prima FAT
		self.fatoffs = self.wSectorsCount * self.wBytesPerSector + self._pos
		# Numero di slot (=cluster) della FAT
		self.fatsize = self.dwTotalLogicalSectors/self.uchSectorsPerCluster
		# Offset dell'area dati (=cluster #2)
		self.dataoffs = self.fatoffs + self.uchFATCopies * self.dwSectorsPerFAT * self.wBytesPerSector + self._pos

	__getattr__ = common_getattr
		
	def __str__ (self):
		return class2str(self, "Settore di avvio FAT32 @%x\n" % self._pos)

	def cl2offset(self, cluster):
		"Calcola l'offset effettivo di un cluster"
		return self.dataoffs + (cluster-2)*self.cluster
		
	def root(self):
		"Offset della root directory"
		return self.cl2offset(self.dwRootCluster)


class DirEntry(object):
	"Decodifica una voce di tabella di directory non exFAT"
	
	layout = { # { offset: (nome, stringa di unpack) }
	0x00: ('sName', '8s'),
	0x08: ('sExt', '3s'),
	0x0B: ('chDOSPerms', 'B'),
	0x0C: ('chFlags', 'B'),
	0x0D: ('chReserved', 'B'),
	0x0E: ('wCTime', '<H'),
	0x10: ('wCDate', '<H'),
	0x12: ('wADate', '<H'),
	0x14: ('wClusterHi', '<H'),
	0x16: ('wMTime', '<H'),
	0x18: ('wMDate', '<H'),
	0x1A: ('wClusterLo', '<H'),
	0x1C: ('dwFileSize', '<I') }

	layout_lfn = { # { offset: (nome, stringa di unpack) }
	0x00: ('chSeqNumber', 'B'), # n° di slot LFN
	0x01: ('sName5', '10s'),
	0x0B: ('chDOSPerms', 'B'), # sempre 0xF
	0x0C: ('chType', 'B'), # sempre 0 per VFAT LFN
	0x0D: ('chChecksum', 'B'),
	0x0E: ('sName6', '12s'),
	0x1A: ('wClusterLo', '<H'), # sempre 0
	0x1C: ('sName2', '4s') }

	def __init__ (self, stream):
		self._i = 0
		self._pos = stream.tell() # posizione iniziale
		self._buf = stream.read(32) # dimensione standard dello slot
		self.stream = stream
		self.LFN = '' # eventuale Long File Name (255 car. max)
		if len(self._buf) != 32:
			raise EndOfStream
		if self._islfn():
			self.islfn = 1
			self._kv = self.layout_lfn.copy()
		else:
			self.islfn = 0
			self._kv = self.layout.copy()
		self._vk = {} # { nome: offset}
		for k, v in self._kv.items():
			self._vk[v[0]] = k
		if self._buf[0] == '\xE5':
			self.deleted = 1
		else:
			self.deleted = 0
		if self._buf[0] in ('\x00', '\xFF'):
			self.unused = 1
		else:
			self.unused = 0
		#~ logging.debug("Decodificata %s", self)

	__getattr__ = common_getattr
		
	def __str__ (self):
		if self.islfn:
			s = "FAT LFN Entry @%x\n"
		else:
			s = "FAT File Entry @%x\n"
		return class2str(self, s % self._pos)
		
	def _islfn(self):
		if self._buf[0x0B] == '\x0F' and \
		self._buf[0x0C] == self._buf[0x1A] == self._buf[0x1B] == '\x00':
			return 1
		else:
			return 0
	
	def dateparse(self, wDate):
		"Decodifica una WORD di data DOS in tuple (anno, mese, giorno)"
		return (wDate>>9)+1980, (wDate>>5)&0xF, wDate&0x1F

	def timeparse(self, wTime):
		"Decodifica una WORD di ora DOS in tuple (ore, minuti, secondi)"
		return wTime>>11, (wTime>>5)&0x3F, wTime&0x1F

	def lfn_checksum(self):
		"Calcola il checksum LFN del nome corto DOS 8+3"
		sum = 0
		for c in self.sName+self.sExt:
			sum = ((sum & 1) << 7) + (sum >> 1) + ord(c)
			sum &= 0xff
		return sum

	def lfn_decode(self, lfn_slots):
		"Assembla e decodifica gli slot LFN riferiti a questa voce"
		csum = self.lfn_checksum()
		name = ''
		i = len(lfn_slots)
		if not (lfn_slots[0].chSeqNumber & 0x40):
			logging.warning("Slot LFN non marcato come finale %s", lfn_slots[0])
		for slot in lfn_slots:
			if slot.chChecksum != csum:
				logging.warning("Checksum del LFN non corrispondente per %s", slot)
				return ''
			if slot.chSeqNumber & 0x3F != i:
				logging.warning("Indice del LFN non corrispondente per %s", slot)
			name = slot.sName5 + slot.sName6 + slot.sName2 + name
			i -= 1
		null = name.find('\x00\x00')
		if null > -1:
			name = name[:null+1] # rimuove *EVENTUALI* NULL superflui
		self.LFN = ('\xFF\xFE' + name).decode('utf16')
		return self.LFN


def fat_recover_slot(boot, fat, slot, destdir=''):
	"Recupera un file da uno slot di directory già decodificato"
	if slot.IsDirectory:
		return
	if not os.path.exists(os.path.join(destdir,slot.Parent)):
		try:
			os.makedirs(os.path.join(destdir,slot.Parent))
		except:
			pass
	if slot.LongName:
		dest = os.path.join(destdir,slot.Parent,slot.LongName)
	else:
		dest = os.path.join(destdir,slot.Parent,slot.ShortName)

	# Apre la catena sorgente come file
	chain = Chain(boot, fat, slot.Start, size=slot.Size)
	out = open(dest, 'wb')
	buf = 1
	while buf:
		buf = chain.read(boot.cluster)
		out.write(buf)
	out.truncate(slot.Size)
	out.close()
	os.utime(dest, (slot.ATime, slot.MTime))
	logging.info("Recuperato %s (%d byte, cluster %d).", dest, slot.Size, slot.Start)
	

def fat_traverse_tree(boot, fat, startcluster, root='.', test=None, action=None, nofat=0):
	"Decodifica una tabella di directory ed esegue un'azione se passa un test (o questo manca)."

	#~ logging.info("Ingresso nella directory %s", root)
	
	class Slot:
		pass
	
	f = boot.stream
	chain = Chain(boot, fat, startcluster, size=nofat, nofat=nofat)
	slots = []
	
	while 1:
		try:
			entry = DirEntry(chain)
		except EndOfStream:
			break
		if entry.deleted: # Deleted
			#~ logging.warning('Rilevato slot di directory cancellato @%x', entry._pos)
			continue
		if entry.unused: # Unused slot area
			#~ logging.warning('Rilevato primo slot di directory non in uso @%x', entry._pos)
			break
		if entry.islfn:
			#~ logging.warning('Rilevato slot di LFN @%x', entry._pos)
			slots += [entry]
			continue
		if entry.sName[0] == '\x2E': # Current (.)/Parent (..) DIR
			#~ logging.warning('Rilevato slot di directory corrente/superiore @%x', entry._pos)
			continue
		if slots: # Se abbiamo raccolto slot di LFN, al primo slot normale che segue...
			entry.lfn_decode(slots)
			slots = []
		if entry.chDOSPerms == 0x8: # Volume Label
			continue
			
		slot = Slot()
		slot.IsDirectory = bool(entry.chDOSPerms & 0x10)
		slot.IsDeleted = entry.deleted
		slot.Parent = root
		slot.ShortName = entry.sName.strip()
		slot.LongName = entry.LFN
		# Nella sola VFAT di Windows NT e seguenti, i bit 3 e 4 nel byte 0xC
		# determinano se nome o estensione vanno resi in minuscolo
		if entry.chFlags & 8:
			slot.ShortName = slot.ShortName.lower()
		if entry.sExt != '   ': # estensione assente
			if entry.chFlags & 16:
				slot.ShortName += '.' + entry.sExt.strip().lower()
			else:
				slot.ShortName += '.' + entry.sExt.strip()

		slot.Size = entry.dwFileSize # 2^32 = 4GiB max
		slot.Start= (entry.wClusterHi << 16) | entry.wClusterLo

		slot.CTime = time.mktime(entry.dateparse(entry.wCDate) + entry.timeparse(entry.wCTime) + (0,0,0))
		slot.MTime = time.mktime(entry.dateparse(entry.wMDate) + entry.timeparse(entry.wMTime) + (0,0,0))
		slot.ATime = time.mktime(entry.dateparse(entry.wADate) + (0,0,0,0,0,0))

		if not test or test(slot):
			if slot.IsDirectory:
				if slot.LongName:
					folder = os.path.join(root, slot.LongName)
				else:
					folder = os.path.join(root, slot.ShortName)
				fat_traverse_tree(boot, fat, slot.Start, folder, test, action=action)
			else:
				action(boot, fat, slot)
		else:
			s = ("file", "directory")[slot.IsDirectory]
			#~ logging.info("Individuato %s (%s) (%s; %d byte, cluster %d).", slot.ShortName, slot.LongName.decode('mbcs'), s, slot.Size, slot.Start)
	
	#~ logging.info("Uscita dalla directory %s", root)


if __name__ == '__main__':
	from datetime import datetime
	def list_slot(boot, fat, slot):
		name = slot.LongName or slot.ShortName
		print "%s   %8d %s" % (datetime.fromtimestamp(slot.MTime).isoformat(), slot.Size, os.path.join(slot.Parent, name))

	def md5_slot(boot, fat, slot, fp):
		import md5
		if not slot.Size or slot.Size > 10**9:
			return
		name = slot.LongName or slot.ShortName
		md = md5.new()
		chain = Chain(boot, fat, slot.Start, size=slot.Size)
		buf = 1
		while buf:
			buf = chain.read(32*(1<<20))
			md.update(buf)
		fp.write( '%s *U:%s\n' % (md.hexdigest(), os.path.join(slot.Parent,name)) )
		print name
		#~ good = md5.new(open(os.path.join("U:",slot.Parent,name),'rb').read()).hexdigest()
		#~ if md.hexdigest() != good:
			#~ print "I checksum MD5 per %s non coincidono!" % name
		#~ else:
			#~ print "Checksum MD5 corretto per", name
		
	action = lambda x, y, z: fat_recover_slot(x, y, z, 'H:')
	
	action = lambda x, y, z: list_slot(x, y, z)
	
	outmd5 = open('checksums.md5','w')
	action = lambda x, y, z: md5_slot(x, y, z, outmd5)

	logging.basicConfig(level=logging.ERROR, filename='FAT32.log', filemode='w')
	
	start = datetime.now()
	
	disk = DiskFile('\\\\.\\z:', 'rb')
	boot = Boot(disk)
	fat = FAT(disk, boot.fatoffs, boot.fatsize)
	fat_traverse_tree(boot, fat, boot.dwRootCluster, '.', test=lambda x: 1, action=action)

	disk.cache.print_stats()

	print "Durata dell'esecuzione:", datetime.now() - start

