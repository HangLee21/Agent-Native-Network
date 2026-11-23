import json,pathlib,tarfile,io,struct,posixpath,re
root=pathlib.Path('runtime/gateway');db=json.loads((root/'selected.json').read_text(encoding='utf-8'));members={};needed={};elfmeta={};glibc_versions=set()
def ardata(path):
 with path.open('rb') as f:
  assert f.read(8)==b'!<arch>\n'
  while True:
   h=f.read(60)
   if not h:raise ValueError('missing data archive')
   n=h[:16].decode().strip().rstrip('/');size=int(h[48:58]);b=f.read(size);f.read(size%2)
   if n.startswith('data.tar'):return b
def elf(data):
 if data[:4]!=b'\x7fELF':return None
 if data[4]!=1 or data[5]!=1:raise ValueError('not little endian ELF32')
 h=struct.unpack_from('<16sHHIIIIIHHHHHH',data,0);machine=h[2];offset=h[5];entsize=h[9];count=h[10];segs=[];dyn=None
 for i in range(count):
  ph=struct.unpack_from('<IIIIIIII',data,offset+i*entsize);typ,off,va,_,filesz,memsz,_,_=ph
  if typ==1:segs.append((va,off,filesz))
  if typ==2:dyn=(off,filesz)
 if not dyn:return machine,[]
 tags=[]
 for pos in range(dyn[0],dyn[0]+dyn[1],8):
  tag,val=struct.unpack_from('<iI',data,pos)
  if tag==0:break
  tags.append((tag,val))
 strva=next((v for t,v in tags if t==5),None);refs=[v for t,v in tags if t==1]
 if not refs:return machine,[]
 loc=next(off+(strva-va) for va,off,size in segs if va<=strva<va+size)
 return machine,[data[loc+v:data.index(b'\0',loc+v)].decode('ascii') for v in refs]
for f in db.values():
 path=root/'debs'/posixpath.basename(f['Filename'])
 with tarfile.open(fileobj=io.BytesIO(ardata(path)),mode='r:*') as tar:
  for entry in tar:
   name=entry.name.lstrip('./')
   if not (name.startswith('usr/lib/python3.4/') or name.startswith('lib/arm-linux-gnueabihf/') or name.startswith('usr/lib/arm-linux-gnueabihf/') or name in ('usr/bin/python3.4','usr/bin/python3.4m','usr/sbin/dnsmasq')):continue
   if '..' in name.split('/'):raise ValueError('unsafe archive path')
   if entry.isfile():
    data=tar.extractfile(entry).read();members[name]=dict(type='file',package=f['Package'],size=len(data))
    val=elf(data)
    if val:
     machine,deps=val
     glibc_versions.update(x.decode('ascii') for x in re.findall(rb'GLIBC_[0-9]+\.[0-9]+(?:\.[0-9]+)?',data))
     if machine!=40:raise ValueError('not ARM: '+name)
     needed[name]=deps;elfmeta[name]=machine
   elif entry.issym() or entry.islnk():members[name]=dict(type='link',target=entry.linkname,package=f['Package'])
provided={posixpath.basename(x) for x in members};base={'libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2','librt.so.1','libutil.so.1','libcrypt.so.1','libresolv.so.2','libnsl.so.1','ld-linux-armhf.so.3','libnss_files.so.2','libnss_dns.so.2'};allneeded={lib for items in needed.values() for lib in items};missing=sorted(allneeded-provided-base);report={'elf_count':len(needed),'needed':sorted(allneeded),'provided':sorted(provided),'base_glibc_assumptions':sorted(allneeded&base),'missing':missing,'glibc_symbol_versions':sorted(glibc_versions),'files':members};(root/'elf-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'elf_count':len(needed),'needed':sorted(allneeded),'base_glibc':sorted(allneeded&base),'glibc_symbol_versions':sorted(glibc_versions),'missing':missing},indent=2))
