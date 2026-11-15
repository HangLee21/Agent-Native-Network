import pathlib,json,tarfile,io,gzip,posixpath,hashlib,copy
root=pathlib.Path('runtime/gateway');db=json.loads((root/'selected.json').read_text(encoding='utf-8'));target=root/'ann-gateway-runtime-jessie-armhf-v1.tar.gz';entries={};skipped=[];licenses={}
def ardata(path):
 with path.open('rb') as f:
  if f.read(8)!=b'!<arch>\n':raise ValueError('invalid deb')
  while True:
   h=f.read(60)
   if not h:raise ValueError('missing data')
   name=h[:16].decode().strip().rstrip('/');size=int(h[48:58]);data=f.read(size);f.read(size%2)
   if name.startswith('data.tar'):return data
for f in db.values():
 deb=root/'debs'/posixpath.basename(f['Filename']);raw=deb.read_bytes()
 if len(raw)!=int(f['Size']) or hashlib.sha256(raw).hexdigest()!=f['SHA256']:raise ValueError('deb checksum mismatch')
 with tarfile.open(fileobj=io.BytesIO(ardata(deb)),mode='r:*') as tar:
  for member in tar:
   if member.name.endswith('/copyright') and member.isfile():licenses[f['Package']]=tar.extractfile(member).read()
   n=member.name
   while n.startswith('./'):n=n[2:]
   if not (n.startswith('usr/lib/python3.4/') or n.startswith('lib/arm-linux-gnueabihf/') or n.startswith('usr/lib/arm-linux-gnueabihf/') or n in ('usr/bin/python3.4','usr/bin/python3.4m','usr/sbin/dnsmasq')):continue
   if n=='usr/lib/python3.4/sitecustomize.py':skipped.append(n);continue
   if not n or n.startswith('/') or '..' in n.split('/'):raise ValueError('unsafe member '+n)
   if member.isdir():continue
   if not (member.isfile() or member.issym() or member.islnk()):raise ValueError('unsupported member '+n)
   item=copy.copy(member);item.name=n;item.uid=item.gid=0;item.uname=item.gname='';item.mtime=0;item.mode&=0o777
   data=tar.extractfile(member).read() if member.isfile() else None
   if member.islnk():
    link=member.linkname
    while link.startswith('./'):link=link[2:]
    if link.startswith('/') or '..' in link.split('/'):raise ValueError('unsafe hardlink')
    item.linkname=link
   elif member.issym():
    link=member.linkname
    if link.startswith('/'):
     resolved=posixpath.normpath(link.lstrip('/'));item.linkname=posixpath.relpath(resolved,posixpath.dirname(n))
    resolved=posixpath.normpath(posixpath.join(posixpath.dirname(n),item.linkname))
    if resolved=='..' or resolved.startswith('../'):raise ValueError('unsafe symlink')
   if n in entries:raise ValueError('duplicate runtime path '+n)
   entries[n]=(item,data)
for name,(info,data) in entries.items():
 if info.issym():
  resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),info.linkname))
  if resolved not in entries and not any(x.startswith(resolved+'/') for x in entries):raise ValueError('unresolved symlink '+name+' -> '+resolved)
 if info.islnk() and info.linkname not in entries:raise ValueError('unresolved hardlink '+name)
assert 'gcc-4.9-base' in licenses and 'dnsmasq-base' in licenses and 'python3.4-minimal' in licenses
wrappers={'bin/python3':'''#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)\nexport PYTHONHOME="$ROOT/usr"\nexport LD_LIBRARY_PATH="$ROOT/lib/arm-linux-gnueabihf:$ROOT/usr/lib/arm-linux-gnueabihf"\nexec "$ROOT/usr/bin/python3.4" "$@"\n''','bin/dnsmasq':'''#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)\nexport LD_LIBRARY_PATH="$ROOT/lib/arm-linux-gnueabihf:$ROOT/usr/lib/arm-linux-gnueabihf"\nexec "$ROOT/usr/sbin/dnsmasq" "$@"\n'''}
with target.open('wb') as raw:
 with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz:
  with tarfile.open(fileobj=gz,mode='w',format=tarfile.PAX_FORMAT) as archive:
   for name in sorted(entries):
    info,data=entries[name];archive.addfile(info,io.BytesIO(data) if data is not None else None)
   for package,data in sorted(licenses.items()):
    info=tarfile.TarInfo('licenses/'+package+'.copyright');info.size=len(data);info.mode=0o644;info.mtime=0;archive.addfile(info,io.BytesIO(data))
   for name,text in sorted(wrappers.items()):
    data=text.encode();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o755;info.mtime=0;archive.addfile(info,io.BytesIO(data))
print(json.dumps({'file_count':len(entries),'skipped':skipped,'license_files':len(licenses),'archive_size':target.stat().st_size,'archive_sha256':hashlib.sha256(target.read_bytes()).hexdigest()},indent=2))
