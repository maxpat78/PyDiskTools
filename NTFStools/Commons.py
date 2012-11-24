# -*- coding: mbcs -*-
import array
import datetime
import logging
import struct

class EndOfStream(Exception):
	pass

class BadRecord(Exception):
	pass

class BadIndex(Exception):
	pass

def class2str(c, s):
	"Enumera in tabella nomi e valori dal layout di una classe"
	keys = c._kv.keys()
	keys.sort()
	for key in keys:
		o = c._kv[key][0]
		v = getattr(c, o)
		if type(v) in (type(0), type(0L)):
			v = hex(v)
		s += '%x: %s = %s\n' % (key, o, v)
	return s


def common_getattr(c, name):
	"Decodifica e salva un attributo in base al layout di classe"
	i = c._vk[name]
	fmt = c._kv[i][1]
	cnt = struct.unpack_from(fmt, c._buf, i+c._i) [0]
	setattr(c, name,  cnt)
	return cnt


def common_update_and_swap(c):
	"Aggiorna i dizionari di classe con le informazioni specifiche dell'attributo"
	if c.uchNonResFlag:
		ko = 64
	else:
		ko = 24
	for k in c.specific_layout.keys(): # aggiorna la tabella con le posizioni effettive
		c._kv[k+ko] = c.specific_layout[k]
	for k, v in c.specific_layout.items():
		c._vk[v[0]] = k+ko
	
	
def common_dataruns_decode(self):
	self.dataruns = (0,0) # tuple di datarun decodificati
	firstrun = 1
	# Di seguito, decodifichiamo una volta per tutte i datarun
	i = self._i + self.wDatarunOffset
	while 1:
		# Legge il primo byte: 2 nibble di indice
		c = struct.unpack("B", self._buf[i])[0]
		if not c: break
		# I 4 bit meno significativi indicano quanti byte compongono 
		# la lunghezza (in cluster) del segmento
		n_length = c & 0xF
		# I 4 bit più significativi indicano quanti byte compongono 
		# l'offset del cluster iniziale
		n_offset = c >> 4
		logging.debug("n_length=%d, n_offset=%d", n_length, n_offset)
		# Legge e determina il n° di cluster del segmento dati
		i += 1
		length = self._buf[i:i+n_length] + array.array('c', (8-n_length)*'\x00')
		length = struct.unpack_from("<Q", length)[0] # ricaviamo sempre una QWORD 128-bit positiva
		# Legge e determina l'offset del cluster iniziale
		# Gli offset successivi al primo partono dall'offset precedente e possono essere negativi!
		i += n_length
		offset = self._buf[i:i+n_offset] + array.array('c', (8-n_offset)*'\x00')
		if not firstrun: # dal secondo datarun in poi, captiamo eventuali offset negativi
			if offset[n_offset-1] >= chr(0x80): # il segno è dato dall'ultimo byte
				offset = self._buf[i:i+n_offset] + array.array('c', (8-n_offset)*'\xFF')
			if n_offset == 1: # era un BYTE originario
				offset = struct.unpack_from("<b", offset[0])[0]
			elif n_offset == 2: # WORD
				offset = struct.unpack_from("<h", offset[:2])[0]
			elif n_offset in (3,4):  # DWORD
				offset = struct.unpack_from("<i", offset[:4])[0]
			else: # QWORD
				offset = struct.unpack_from("<q", offset)[0]
		else:
			offset = struct.unpack_from("<Q", offset)[0]
			firstrun = 0
		if not offset:
			logging.debug("File sparse non supportati!")
		# calcola e salva lunghezza e offset del run in base al cluster effettivo
		logging.debug("length=%d offset=%d prevoffset=%d", length, offset, self.dataruns[-1])
		self.dataruns += (length*4096, (offset*4096+self.dataruns[-1])) # ATTENZIONE! Correggere con la dimensione EFFETTIVA del cluster!
		i += n_offset
	logging.debug("decoded dataruns @%d:\n%s", self._i, self.dataruns)

def nt2uxtime(t):
	"Converte data e ora dal formato NT a Python (Unix)"
	# NT: lassi di 100 nanosecondi dalla mezzonotte dell'1/1/1601
	# Unix: secondi dall' 1/1/1970
	# La differenza è di 134774 giorni o 11.644.473.600 secondi
	return datetime.datetime.utcfromtimestamp(t/10000000 - 11644473600)

def common_fixup(self):
	"Verifica e applica il fixup a record MFT, indici, log record"
	# la WORD di fixup è all'inizio dell'Update Sequence Array (di WORD)
	fixupn = self._buf[self.wUSAOffset:self.wUSAOffset+2]
	for i in range(1, self.wUSASize):
		fixuppos = i*512 - 2 # ultima WORD del settore
		if fixupn != self._buf[fixuppos:fixuppos+2]:
			print "Fixup errato!"
		offs = self.wUSAOffset+2*i # offset della WORD da sostituire nello USA
		self._buf[fixuppos:fixuppos+2] = self._buf[offs:offs+2]
