'use strict';
const FleetLabels=(()=>{
 const mac=x=>String(x||'').trim().toLowerCase(),valid=x=>/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(x);
 function parse(data){if(!data||data.schema_version!==1||!Array.isArray(data.nodes))throw Error('节点配置格式或版本不正确');const ids=new Set(),map=new Map();for(const row of data.nodes){const id=row.node_id,m=mac(row.mac);if(!Number.isSafeInteger(id)||id<1||!valid(m))throw Error('节点编号或 MAC 无效');if(ids.has(id)||map.has(m))throw Error('节点编号或 MAC 重复');ids.add(id);map.set(m,id);}return map;}
 function label(map,id){const m=mac(id);if(!valid(m))return null;
  // A node missing from the roster is still a real, live node: it just has no number yet.
  // Showing the MAC tail stays readable, whereas "UNSET" read like a fault on every
  // freshly flashed board.
  return map.has(m)?String(map.get(m)):m.slice(-8);}
 return{parse,label};
})();
