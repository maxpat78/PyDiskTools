# -*- coding: mbcs -*-
import array
from collections import Counter, OrderedDict
import logging

"""
Come dovrebbe operare purge():
- determinare la frequenza minima di servizio di un blocco; quindi
- rimuovere il blocco più anticamente inserito, con quella frequenza.

In tal modo, gli elementi meno richiesti e più vecchi sono eliminati per primi, 
dando modo a quelli più recenti di avere più chance di richiamo.

*** Proteggere l'ultimo elemento servito dall'eliminazione? ***

Si possono usare diverse strategie per la manutenzione della cache.

Una cache non purgata può consumare memoria all'infinito, e ciò non è auspicabile.

Dai risultati di cui innanzi, da test su un filesystem tipico di una chiavetta, appare che le prestazioni migliori
(in termini di minor tempo per la manutenzione) si ottengono azzerando completamente la cache al 
superamento della soglia.

Il caching del solo ultimo blocco letto non si rivela tanto penalizzante (solo 5" di differenza).

Il metodo più lento (di 1 minuto!) è invece quello che rimuove il più antico blocco meno usato, anche
perché l'elaborazione deve essere ripetuta a ogni inserimento di blocco successivo al superamento
della soglia.

Tale metodo, e anche quello che rimuove la metà meno usata dei blocchi, sarebbero molto più efficienti
se si disponesse di una tabella già ordinata per frequenza di servizio e si potesse rimuovere tutti gli 
elementi voluti in *una* sola operazione.

FAT32 3,12GB in 12110 file e 491 cartelle
no purge		6:37
purge all		6:45
purge half		6:49
simple cache	6:50
purge least used	7:45
"""
class Cache(object):
	def __init__ (self, items=2000, itemsize=4096):
		self.items = items
		self.itemsize = itemsize
		# dizionario di blocchi, ordinati per tempo di inserimento
		self.cache = OrderedDict()
		self.hits = OrderedDict()

	def update(self, disk):
		if len(disk.buf) > self.itemsize:
			return
		if disk.si in self.cache and len(disk.buf) <= len(self.cache[disk.si]):
			self.hits[disk.si] += 1
			return
		if len(self.cache) > self.items:
			self.purge()
		self.cache[disk.si] = disk.buf
		self.hits[disk.si] = 0
	
	def purge0(self):
		"*NON* azzera la cache: ma spreca memoria illimitatamente!"
		pass
		
	def purge1(self):
		"Azzera la cache non appena piena"
		self.cache = OrderedDict()
		self.hits = OrderedDict()
		
	def purge2(self):
		"Elimina il primo blocco meno frequentemente usato"
		# Determina la frequenza minima di riciclo di un blocco
		minfreq = Counter(self.hits).most_common()[-2][1]
		# Determina il blocco più vecchio con tale frequenza
		i = self.hits.values().index(minfreq)
		# Determina il n° di blocco corrispondente
		key = self.hits.keys()[i]
		# Lo rimuove dalla cache
		del self.cache[key]
		del self.hits[key]

	def purge3(self):
		"Elimina la metà dei blocchi meno usati"
		#Errore nel canc. chiave inesistente?
		half_commons = Counter(self.hits).most_common(self.items/2)
		g = set(self.hits)
		h = set(half_commons)
		for key in (g - h):
			del self.cache[key]
			del self.hits[key]
		#~ self.hits = OrderedDict(dict(half_commons))
	
	purge = purge1
	
	def retrieve(self, disk):
		if disk.si in self.cache and disk.asize <= len(self.cache[disk.si]):
			disk.buf = self.cache[disk.si]
			return 1
		return 0

	def print_stats(self):
		#~ logging.info("Voci di cache in memoria:", len(self.hits))
		print "Voci di cache in memoria:", len(self.hits)
		#~ logging.info("Voci di cache riscontrate:")
		print "Voci di cache riscontrate:"
		for i, freq in self.hits.iteritems():
			if freq < 1: continue
			logging.info("Blocco %Xh, %d volte.", i, freq)
			print "Blocco %Xh, %d volte." % (i, freq)


class SimpleCache(object):
	"Semplice cache che registra e serve solo l'ultimo blocco letto"
	def __init__ (self, itemsize=4096):
		self.itemsize = itemsize
		self.hits = 0
		
	def update(self, disk):
		pass
		
	def retrieve(self, disk):
		if disk.si == disk.lastsi and len(disk.buf) == disk.asize:
			self.hits += 1
			return 1
		return 0
		
	def print_stats(self):
		print "Riscontri dalla cache", self.hits
		
		
#~ diskcache = Cache()
diskcache = SimpleCache()


class DiskFile(object):
	"""Un disco può essere aperto come un file, tuttavia: 1) read, write, seek devono essere allineate
	a settori di 512 byte; 2) seek dalla fine non è ammesso; 3) seek oltre la fine seguito
	da una lettura non dà errori."""
	
	def __init__(self, name, mode='rb', buffering=0, size=0):
		self.pos = 0 # posizione lineare
		self.si = 0 # n° di blocco
		self.so = 0 # offset nel blocco
		self.lastsi = 0 # ultimo blocco letto dal *disco*
		self.size = size # dimensione del filesystem (se nota)
		self._file = open(name, mode, buffering)
		self.buf = ''
		self.blocksize = diskcache.itemsize
		self.cache = diskcache

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
		self.si = self.pos / self.blocksize
		self.so = self.pos % self.blocksize
		if self.si == self.lastsi:
			return # non sposta la testina di lettura se il settore è invariato
		self._file.seek(self.si*self.blocksize)
		#~ logging.debug("DiskFile seek @%Xh", self.si*self.blocksize)
		#~ logging.debug("si=%Xh lastsi=%Xh so=%Xh", self.si,self.lastsi,self.so)
		
	def tell(self): return self.pos
		
	def read(self, size=-1):
		self.seek(self.pos)
		# Se la q.tà è negativa, la aggiusta...
		if size < 0:
			size = 0
			if self.size: size = self.size
		# Se la q.tà eccede la dimensione del file, la limita a essa
		if self.size and self.pos + size > self.size:
			size = self.size - self.pos
		se = (self.pos+size)/self.blocksize
		if (self.pos+size)%self.blocksize:
			se += 1
		self.asize = (se - self.si) * self.blocksize # n° di blocchi interi da leggere
		# Se la q.tà da leggere è nella cache...
		if self.cache.retrieve(self):
			#~ logging.debug("letti %d byte dalla cache" % self.asize)
			self.pos += size
			self.cache.update(self)
			return self.buf[self.so : self.so+size]
		self.buf = array.array('c')
		self.buf.fromfile(self._file, self.asize)
		self.lastsi = self.si
		self.pos += size
		#~ logging.debug("letti %d byte dal disco" % self.asize)
		self.cache.update(self)
		return self.buf[self.so : self.so+size]
