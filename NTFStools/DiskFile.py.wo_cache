# -*- coding: mbcs -*-
import array
import logging


class DiskFile(object):
	"""Un disco può essere aperto come un file, tuttavia: 1) read, write, seek devono essere allineate
	a settori di 512 byte; 2) seek dalla fine non è ammesso; 3) seek oltre la fine seguito
	da una lettura non dà errori."""
	
	def __init__(self, name, mode='r', buffering=0, size=0):
		self.pos = 0 # posizione lineare
		self.si = 0 # n° di blocco
		self.so = 0 # offset nel blocco
		self.lastsi = 0 # ultimo blocco letto dal *disco*
		self.size = size # dimensione del filesystem (se nota)
		self._file = open(name, mode, buffering)
		self.buf = ''
		self.cachesize = 4096

	def setcache(self, size=4096):
		self.buf = ''
		# unità di lettura o blocco (dev'essere multiplo del settore di 512 byte)
		self.cachesize = size
		self.lastsi = -1
		
	def seek(self, offset, whence=0):
		if whence == 1:
			self.pos += offset
		elif whence == 2:
			if self.size and offset < self.size:
				self.pos = self.size - offset
			elif self.size and offset >= self.size:
				self.pos = 0
		else:
			self.pos = offset
		self.si = self.pos / self.cachesize
		self.so = self.pos % self.cachesize
		if self.si == self.lastsi:
			return # non sposta la testina di lettura se il settore è invariato
		self._file.seek(self.si*self.cachesize)
		logging.debug("DiskFile seek @%Xh", self.si*self.cachesize)
		logging.debug("si=%Xh lastsi=%Xh so=%Xh", self.si,self.lastsi,self.so)
		
	def tell(self): return self.pos
		
	def read(self, size=-1):
		# Se la q.tà è negativa, la aggiusta...
		self.seek(self.pos)
		if size < 0:
			size = 0
			if self.size: size = self.size
		# Se la q.tà eccede la dimensione del file, la limita a essa
		if self.size and self.pos + size > self.size:
			size = self.size - self.pos
		se = (self.pos+size)/self.cachesize
		if (self.pos+size)%self.cachesize:
			se += 1
		self.asize = (se - self.si) * self.cachesize # n° di blocchi interi da leggere
		# Se la q.tà da leggere non cade nel buffer risultante dalla precedente lettura...
		if self.si == self.lastsi and self.asize == len(self.buf):
			logging.debug("letti %d byte dalla cache", self.asize)
			self.pos += size
			return self.buf[self.so : self.so+size]
		self.buf = array.array('c')
		self.buf.fromfile(self._file, self.asize)
		self.lastsi = self.si
		self.pos += size
		logging.debug("letti %d byte dal disco", self.asize)
		return self.buf[self.so : self.so+size]
