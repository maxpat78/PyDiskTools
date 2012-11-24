# -*- coding: mbcs -*-
import array
import fnmatch
import logging
import os
import StringIO
import struct
import sys
from NTFStools.Boot import *
from NTFStools.DiskFile import *
from NTFStools.Index import *
from NTFStools.Record import *


def ntfs_get_filename(mftrecord):
	"Trova il nome (più) lungo appropriato associato al record MFT"
	names = mftrecord.find_attribute("$FILE_NAME")
	n = 0
	wanted = ''
	for name in names:
		if len(name.FileName) > n:
			n = len(name.FileName)
			wanted = name.FileName
	return wanted
	
def ntfs_copy_file(mftrecord, outfile=None):
	"Copia un file da un record MFT alla cartella attiva (o alla diversa destinazione indicata)"
	selected = mftrecord.find_attribute("$DATA")[-1].file
	if not outfile:
		outfile = ntfs_get_filename(mftrecord)
	if type(outfile) == type(file): # può essere un file già aperto
		outstream = outfile
	else:
		outstream = open(outfile,'wb')
	while 1:
		s = selected.read(4096*1024)
		if not s:
			break
		outstream.write(s)
	outstream.close()
	

def ntfs_open_file(abspathname, mftstream, diskstream):
	"Apre un file di cui è indicato il percorso assoluto, navigando attraverso gli indici"
	tail = ' '
	head = abspathname
	path = []
	while tail != '':
		head, tail = os.path.split(head)
		path += [tail]
	path.reverse()
	mftstream.seek(5*1024) # salta direttamente a ROOT
	rfile = Record(mftstream, diskstream)
	indx = None
	for obj in path:
		if not obj:
			obj = '.' # ROOT
			
		logging.debug("Ricerca di <%s> nel percorso <%s>", obj, path)
		
		if indx: # Se c'è un indice aperto...
			for name in indx.next():
				logging.debug("Esamino voce di indice <%s>", name.FileName)
				if fnmatch.fnmatch(name.FileName, obj):
					logging.debug("<%s> concorda con <%s>: selezione record $MFT %s", obj, name.FileName, hex(name.u64mftReference & 0x0000FFFFFFFFFFFF))
					rfile = rfile.next(name.u64mftReference & 0x0000FFFFFFFFFFFF)
					if path.index(obj)+1 == len(path): # ultimo elemento == file
						return rfile
					indx = None
					break
					
		while 1: # Cerca nella $MFT il nome di oggetto voluto
			attr = rfile.find_attribute("$FILE_NAME")
			if attr:
				for name in attr: # Per ogni nome: corto, lungo...
					if fnmatch.fnmatch(name.FileName, obj):
						logging.debug("<%s> concorda con <%s>: apertura dell'indice", obj, name.FileName)
						attr = rfile.find_attribute("$INDEX_ALLOCATION")
						if attr:
							bitmap = rfile.find_attribute("$BITMAP")[0]
							indx = Index(attr[0].file, bitmap, 0)
							break
						# Se non c'è 0xA0, allora è residente in 0x90!
						attr = rfile.find_attribute("$INDEX_ROOT")
						if attr and not attr[0].uchNonResFlag:
							indx = Index(attr[0].file, None, 1)
							logging.debug("nota: indice residente")
							break
			if indx: break
			rfile = rfile.next()
			logging.debug("selezione del prossimo record $MFT")
