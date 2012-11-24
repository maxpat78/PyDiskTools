# -*- coding: mbcs -*-
import array
import logging

class DatarunStream(object):
	def __init__ (self, dataruns, size, diskstream):
		self._runs = dataruns
		self._disk = diskstream
		self.curdatarun = 0 # indice del datarun per l'offset attuale
		self.curdatarunpos = 0 # posizione nel datarun corrente
		self.size = size # dimensione totale dello stream virtuale
		self.seekpos = 0 # posizione virtuale nello stream virtuale

	def read(self, size=-1):
		buf = array.array('c')
		logging.debug("read() loop with size=%d", size)
		
		# legge tutto ciò che avanza, non oltre la fine dello stream virtuale
		if size < 0 or self.seekpos + size > self.size:
			size = self.size - self.seekpos
			logging.debug("size adjusted to %d", size)
			
		while size > 0:
			self.seek(self.seekpos) # carica i dati relativi al datarun corrente
			# non legge oltre la fine del datarun corrente
			if self.curdatarunpos + size <= self._runs[self.curdatarun]:
				logging.debug("reading %d bytes streampos=@%d, datarunpos=%d", size, self.seekpos, self.curdatarunpos)
				buf += self._disk.read(size)
				self.seekpos += size
				break
			else:
				readsize = self._runs[self.curdatarun] - self.curdatarunpos # byte residui nel run
				if not readsize:
					logging.debug("readsize == 0 ending loop")
					break
				buf += self._disk.read(readsize)
				self.seekpos += readsize
				size -= readsize
				logging.debug("read truncated to %d bytes (%d byte last) @streampos=%d, datarunpos=%d", readsize, size, self.seekpos, self.curdatarunpos)
		return buf
		

	def tell(self):
		return self.seekpos
		
	def seek(self, offset, whence=0):
		if whence == 1:
			self.seekpos += offset
		elif whence == 2:
			self.seekpos = self.size - offset
		else:
			self.seekpos = offset
		i, todo = 0, self.seekpos
		for i in range(2, len(self._runs), 2):
			# se la posizione supera (o eguaglia: poiché dobbiamo leggere
			# il byte SUCCESSIVO) il primo intervallo...
			self.curdatarun = i
			self.curdatarunpos = todo
			if todo >= self._runs[i]:
				todo -= self._runs[i] # ,,,avanza al prossimo datarun
				continue
			else:
				break
		# Trovato il datarun in cui cade la posizione finale, eseguiamo il seek dal suo offset
		logging.debug("seek @%x, datarun=%d, relativepos=%x", self.seekpos, i-2, todo)
		# BUGBUG: pare che un problema con Index() si annidi qui: dev'essere il disco REALE, non quello emulato dal datarun, ke fa seek!
		self._disk.seek(self._runs[i+1] + todo)
