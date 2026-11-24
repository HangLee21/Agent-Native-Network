"""Adapter from mission-local envelopes to D-045's actual network API.

Pending D-045 freeze: this adapter is provisional and may only be used in
synthetic tests until its dependency and data audit are accepted.
"""
from __future__ import annotations
from network import Network


class MissionTransport:
    def __init__(self,config,seed,online_schedule=None):
        self.net=Network(config,seed)
        self.online_schedule=online_schedule
        self.outcomes=[]
        self.topologies=[]
        self.enqueued=[]
        self.previous_positions=None
        self.previous_time=None

    def advance(self,now,positions):
        mapping={i:[float(v) for v in row] for i,row in enumerate(positions)}
        online=self.online_schedule(now,len(positions)) if self.online_schedule else None
        self.net.update(now,mapping,online)
        self.topologies.append(self.net.topology())
        self.outcomes.extend(self.net.drain(now))
        result={i:[] for i in mapping}
        for i in mapping:
            for msg in self.net.poll(i,now):
                kind=msg['kind']; payload=msg['payload']
                if kind=='SAMPLE':
                    translated_kind='SAMPLE'; translated=payload
                elif kind=='TASK_INTENT':
                    translated_kind='TASK_INTENT'
                    translated={'target_index':int(payload['region_id']),'expires_s':float(payload['expires_at']),
                                'height_m':float(payload['height_m'])}
                else:
                    translated_kind=kind; translated=payload
                result[i].append({'kind':translated_kind,'sender':msg['source'],'receiver':i,
                                  'created_s':msg['created_at'],'delivered_s':msg['completed_at'],
                                  'network_message_id':msg['message_id'],'payload':translated})
        return result

    def send(self,now,positions,outgoing):
        if self.previous_positions is None:
            velocities=[[0.,0.,0.] for _ in positions]
        else:
            dt=now-self.previous_time
            velocities=[[(float(v)-float(old))/dt for v,old in zip(p,q)] if dt>0 else [0.,0.,0.]
                        for p,q in zip(positions,self.previous_positions)]
        for i,p in enumerate(positions):
            payload={'node_id':i,'position':[float(x) for x in p], 'velocity':velocities[i], 'timestamp':now}
            frame=self.net.send(now,i,'NODE_STATE',payload)
            self.enqueued.append({'created_s':now,'sender':i,'kind':'NODE_STATE','frame_id':frame})
        for item in outgoing:
            if item['kind']=='SAMPLE':
                payload=item['payload']; kind='SAMPLE'
            elif item['kind']=='TASK_INTENT':
                intent=item['payload']; kind='TASK_INTENT'
                payload={'region_id':intent['target_index'],'utility':intent['utility'],'eta':intent['eta_s'],
                         'expires_at':intent['expires_s'],'height_m':intent['height_m']}
            elif item['kind'] in ('MAP_SUMMARY','TASK_UPDATE'):
                kind=item['kind']; payload=item['payload']
            else: raise ValueError('unsupported outgoing mission kind')
            frame=self.net.send(now,int(item['sender']),kind,payload)
            self.enqueued.append({'created_s':now,'sender':item['sender'],'kind':kind,'frame_id':frame})
        self.previous_positions=positions.copy(); self.previous_time=now

    def snapshot(self,now):
        self.outcomes.extend(self.net.drain(now))
        return {'metrics':self.net.metrics(now),'outcomes':self.outcomes,
                'topologies':self.topologies,'enqueued':self.enqueued}
