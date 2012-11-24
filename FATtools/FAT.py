# -*- coding: mbcs -*-
import logging
import struct
from NTFStools.Commons import *
from NTFStools.DiskFile import DiskFile

"""
Nota sulle prestazioni
======================
Una lettura sequenziale di 64M da chiavetta USB, che impiega 3 secondi, ne
richiede ben *NOVE* se suddivisa in segmenti da 512 byte!!!

Per avere prestazioni decenti in lettura, si ricorre a due strategie:

1) creare due DiskFile separati - uno per la FAT, con la propria cache e un altro per
il contenuto dei file: si evitano in parte continui salti indietro per esaminare la FAT
prima di accedere a ogni cluster dati.

2) leggere il contenuto a segmenti contigui, determinando prima della lettura
l'estensione di ciascuna sequenza non frammentata di cluster.

Ciò incrementa notevolmente le prestazioni.

Tuttavia, nel calcolo del MD5 su ca. 150 MiB in 320 file di varie taglie, Python impiega
10" contro i 5" di un'utilità apposita.

Tale divario relativo si accorcia su ca. 989MiB in 430 file (53 vs. 41).

Aumentare la dimensione della "cache read-ahead" sembra determinare un rallentamento.
Egualmente, assegnare un DiskFile a ogni oggetto Chain.
"""


class FAT(object):
	"Decodifica una FAT (12, 16, 32 o EX) dal disco"
	def __init__ (self, stream, offset, clusters, bitsize=32, exfat=0):
		# Crea uno stream autonomo, con propria cache
		self.stream = DiskFile(stream._file.name, stream._file.mode)
		self.offset = offset # offset iniziale della FAT in esso
		self.size = clusters # numero di cluster (=slot della FAT)
		self.bits = bitsize # bit dello slot (12, 16 o 32)
		self.exfat = exfat # se si tratta di EXFAT
		self.reserved = 0x0FF0
		self.bad = 0x0FF7
		self.last = 0x0FF8
		if bitsize == 16:
			self.reserved |= 0xFF00
			self.bad |= 0xFF00
		elif bitsize ==32:
			self.reserved |= 0x0FFFFF00 # FAT32 usa solo 28 bit
			self.bad |= 0x0FFFFF00
			self.last |= 0x0FFFFF00
			if exfat:
				self.reserved |= 0xF0000000 # EXFAT li usa tutti
				self.bad |= 0xF0000000
				self.last |= 0xF0000000
				
	def __getitem__ (self, index):
		self.stream.seek(self.offset+(index*self.bits)/8)
		if self.bits == 32:
			n, fmt = 4, '<I'
		else:
			n, fmt = 2, '<H'
		slot = struct.unpack(fmt, self.stream.read(n))[0]
		if self.bits == 12:
			# Ricava i 12 bit di interesse
			if index % 2: # indice dispari
				slot = slot >> 4
			else:
				slot = slot & 0x0FFF
		return slot

	def isvalid(self, index):
		"Determina se il numero di cluster dati è valido per questa FAT"
		if (index > 1 and index <= self.size) or self.islast(index) or self.isbad(index):
			return 1
		logging.debug("indice di cluster non valido: %x", index)
		return 0
		
	def islast(self, index):
		"Determina se è l'ultimo cluster della catena"
		return self.last <= index <= self.last+7 # *F8 ... *FF
		
	def isbad(self, index):
		return index == self.bad


class Chain(object):
	"Accede a una catena di cluster come a un file"
	def __init__ (self, boot, fat, cluster, size=0, nofat=0):
		# Crea uno stream autonomo, con propria cache
		self.stream = boot.stream
		self.boot = boot
		self.fat = fat
		self.start = cluster # cluster iniziale
		self.size = size # dimensione della catena, se disponibile
		self.nofat = nofat # privo di catena FAT (=contiguo)
		self.pos = 0 # virtual stream linear pos
		# Virtual Cluster Number (indice del cluster nella catena)
		self.vcn = -1
		# Virtual Cluster Offset (posizione nel VCN)
		self.vco = -1
		self.lastvlcn = (0, cluster) # VCN e LCN dell'ultimo cluster esaminato
		#~ logging.debug("Catena di cluster @%Xh", cluster)
	
	def maxrun4len(self, length):
		"""Calcola il più lungo segmento contiguo, inferiore a una data misura,
		che può essere letto dalla posizione corrente"""
		startindex = self.lastvlcn[0]
		maxchunk = self.boot.cluster
		while 1:
			last = self.lastvlcn[1]
			next = self.fat[last]
			if self.fat.islast(next):
				break
			if not self.fat.isvalid(next):
				raise EndOfStream
			if next == last+1:
				self.lastvlcn = (self.lastvlcn[0]+1, next)
				maxchunk = self.boot.cluster * (self.lastvlcn[0]-startindex)
				if  maxchunk > length:
					break
				continue
			else:
				break
		#~ logging.debug("rilevati %d byte (%d cluster) contigui dal VCN %d", maxchunk, self.lastvlcn[0]-startindex or 1, startindex)
		return maxchunk
		
	def tell(self): return self.pos
	
	def seek(self, offset, whence=0):
		if whence == 1:
			self.pos += offset
		elif whence == 2:
			if self.size:
				self.pos = self.size - offset
		else:
			self.pos = offset
		self.vcn = self.pos / self.boot.cluster # n-esimo cluster della catena
		self.vco = self.pos % self.boot.cluster # offset in detto cluster
		self.realseek()
		
	def realseek(self):
		#~ logging.debug("VCN=%d VCO=%d", self.vcn,self.vco)
		if self.size and self.pos >= self.size:
			#~ logging.debug("Fine catena al VCN %d", self.vcn)
			self.vcn = -1
			return
		if self.nofat:
			cluster = self.start + self.vcn
			if cluster > self.start + self.size/self.boot.cluster:
				self.vcn = -1
		else:
			# Se abbiamo raggiunto un anello della catena, precedente
			# e più vicino...
			if self.lastvlcn[0] < self.vcn:
				si = self.lastvlcn[0]
				cluster = self.lastvlcn[1]
			else:
				si = 0
				cluster = self.start
			for i in range(si, self.vcn):
				cluster = self.fat[cluster]
				if not self.fat.isvalid(cluster):
					raise EndOfStream
			self.lastvlcn = (self.vcn, cluster)
			if self.fat.islast(cluster):
				self.vcn = -1
		#~ logging.debug("prossimo cluster: VCN=%d, LCN=%Xh [%Xh:] @%Xh", self.vcn, cluster, self.vco, self.boot.cl2offset(cluster))
		self.stream.seek(self.boot.cl2offset(cluster)+self.vco)

	def read(self, size=-1):
		#~ logging.debug("chiesti %d byte dalla posizione %Xh", size, self.pos)
		self.seek(self.pos)
		# Se la q.tà è negativa, la aggiusta...
		if size < 0:
			size = 0
			if self.size: size = self.size
		# Se la q.tà eccede la dimensione del file, la limita a essa
		if self.size and self.pos + size > self.size:
			size = self.size - self.pos
		buf = array.array('c')
		if self.nofat: # i cluster sono tutti contigui
			if not size or self.vcn == -1:
				return buf
			buf += self.stream.read(size)
			self.pos += size
			#~ logging.debug("letti %d byte contigui, VCN=%Xh[%Xh:]", len(buf), self.vcn, self.vco)
			return buf
		while 1:
			if not size or self.vcn == -1:
				break
			n = min(size, self.maxrun4len(size))
			buf += self.stream.read(n)
			size -= n
			self.pos += n
			self.seek(self.pos)
		#~ logging.debug("letti %d byte, VCN=%Xh[%Xh:]", len(buf), self.vcn, self.vco)
		return buf
