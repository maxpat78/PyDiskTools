# -*- coding: mbcs -*-
import array
import logging

class DiskFile(object):
	"""Un disco può essere aperto come un file, tuttavia: 1) read, write, seek devono essere allineate
	a settori di 512 byte; 2) seek dalla fine non è ammesso; 3) seek oltre la fine seguito
	da una lettura non dà errori."""
	
	def __init__(self, name, mode='r', buffering=0, size=0):
		self.pos = 0 # posizione lineare
		self.si = 0 # n° di settore
		self.so = 0 # offset nel settore
		self.size = size # dimensione del filesystem (se nota)
		self._file = open(name, mode, buffering)

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
		self.si = self.pos / 512
		self.so = self.pos % 512
		self._file.seek(self.si*512)
		logging.debug("done disk seek @%x", self.si*512)
		logging.debug("si=%X so=%X", self.si,self.so)
		
	def tell(self): return self.pos
		
	def read(self, size=-1):
		# NOTA 1: se l'inizio si trova alla fine di un settore, e la quantità da leggere è piccola
		# dobbiamo leggere il settore contenente l'inizio *E* quello successivo: correggere!
		
		# Se la q.tà è negativa, la aggiusta...
		if size < 0:
			size = 0
			if self.size: size = self.size
		# Se la q.tà eccede la dimensione del file, la limita a essa
		if self.size and self.pos + size > self.size:
			size = self.size - self.pos
		se = (self.pos+size)/512
		if (self.pos+size)%512:
			se += 1
		alignedSize = (se - self.si) * 512
		buf = array.array('c')
		buf.fromfile(self._file, alignedSize)
		logging.debug("done disk read %d bytes", alignedSize)
		self.pos += size
		self.seek(self.pos)
		return buf[self.so : self.so+size]
