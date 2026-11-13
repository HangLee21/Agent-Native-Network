"""M-020 plan generation only: no ports, servers, files from client paths or runs."""
from pathlib import Path
import copy,hashlib,itertools,json,math,sys

class PlanError(ValueError):
    def __init__(self,code,message):
        super().__init__(message);self.code=code

def fail(code,message):raise PlanError(code,message)
def integer(x,lo,hi,name):
    if type(x) is not int or not lo<=x<=hi:fail('invalid_'+name,f'{name} must be integer {lo}..{hi}')
    return x

class PlanLibrary:
    def __init__(self,repo_root=None):
        self.root=Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.source=self.root/'simulation/outputs/E1-016/20261107-02-five-real/AB/input.json'
        bindings=json.loads((self.root/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text(encoding='utf-8'))
        self.labels=bindings.get('labels',bindings.get('bindings'))
        self.base=json.loads(self.source.read_text(encoding='utf-8'))
        if set(self.labels)!=set('ABCDE') or len(set(self.labels.values()))!=5:raise ValueError('invalid fixed bindings')
        if set(self.base['nodes'])!=set(self.labels.values()):raise ValueError('model and bindings differ')
        self.back={v:k for k,v in self.labels.items()}

    def list_models(self):
        return [dict(id='assumed-five-v1',label='原五板假设信道模型（非测量）',source_kind='assumption',offline_preview=True,
                     source_path=str(self.source.relative_to(self.root)).replace('\\','/'),source_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
                     verified_scope='Original 12 SOCP cases solved and package-03 functionality tested; coefficients not RF calibrated or current link measurements',
                     node_labels=list('ABCDE'),bindings=copy.deepcopy(self.labels),unit='dimensionless model rate',default_demand=.05,qos=.9,
                     supports_node_subsets=True,edges=[dict(src=a,dst=b,mean=self.base['mean'][self.base['nodes'].index(self.labels[a])][self.base['nodes'].index(self.labels[b])]) for a in 'ABCDE' for b in 'ABCDE' if a!=b],
                     limitation='Old successful packets do not prove current adjacency/availability. H supplies live state separately.')]

    def plan(self,request,*,available_nodes=None,live_status=None):
        try:return self._plan(request,available_nodes,live_status)
        except PlanError as e:return dict(ok=False,error=dict(code=e.code,message=str(e)))
        except (TypeError,KeyError,ValueError,OverflowError) as e:return dict(ok=False,error=dict(code='invalid_request_or_coefficients',message=str(e)))

    def _plan(self,q,available,live):
        if not isinstance(q,dict):fail('invalid_request','object required')
        src,dst=q.get('src'),q.get('dst');mode=q.get('mode')
        if src not in self.labels or dst not in self.labels or src==dst:fail('invalid_endpoints','choose two different A..E nodes')
        if mode not in ('mid','hops','manual'):fail('invalid_mode','mode must be mid/hops/manual')
        if q.get('model_id','assumed-five-v1')!='assumed-five-v1':fail('unknown_model','only catalog model IDs allowed, not file paths')
        count=integer(q.get('count',1),1,10,'count')
        if available is not None and (not isinstance(available,(list,tuple,set)) or any(x not in self.labels for x in available)):fail('invalid_live_nodes','server available_nodes must be A..E list')
        selected=q.get('node_set')
        if selected is None:selected=sorted(available) if available and src in available and dst in available else list('ABCDE')
        if not isinstance(selected,list) or not 2<=len(selected)<=5 or any(x not in self.labels for x in selected) or len(set(selected))!=len(selected) or src not in selected or dst not in selected:fail('invalid_node_set','2..5 unique nodes including endpoints required')
        selected=sorted(selected)
        edges={(a,b) for a in selected for b in selected if a!=b and self.base['mean'][self.base['nodes'].index(self.labels[a])][self.base['nodes'].index(self.labels[b])]>0}
        if 'graph_edges' in q:
            raw=q['graph_edges']
            if not isinstance(raw,list) or any(not isinstance(x,list) or len(x)!=2 or any(not isinstance(z,str) for z in x) for x in raw):fail('invalid_graph','graph_edges must be directed [src,dst] pairs')
            requested={tuple(e) for e in raw}
            if not requested<=edges:fail('invalid_graph','selected edges must be positive model edges within node_set')
            edges=requested
        if not self._can_reach(src,dst,edges):fail('no_path','destination unreachable in selected graph')
        chain=None;answer=None
        if mode=='hops':
            k=integer(q.get('hops'),1,4,'hops')
            if k>len(selected)-1:fail('infeasible_hops','not enough distinct nodes for exact hop count')
            paths=[]
            for middle in itertools.permutations([x for x in selected if x not in (src,dst)],k-1):
                path=[src,*middle,dst]
                if all((a,b) in edges for a,b in zip(path,path[1:])):paths.append(path)
            if not paths:fail('infeasible_hops','no simple path with exactly requested edges')
            chain=min(paths)
        elif mode=='manual':
            via=q.get('via',[])
            if not isinstance(via,list) or len(via)>3 or any(x not in selected for x in via):fail('invalid_via','via must be up to3 selected node labels')
            chain=[src,*via,dst]
            if len(set(chain))!=len(chain):fail('cyclic_path','manual path must be simple, no repeated endpoint or relay')
            if any((a,b) not in edges for a,b in zip(chain,chain[1:])):fail('missing_edge','manual path contains unavailable/unselected directed edge')
        nodes=[self.labels[x] for x in selected]
        if chain:
            update=dict(schema='mid.network_update.v1',nodes=nodes,flows=[dict(src=self.labels[src],dst=self.labels[dst])],routes=[dict(node=self.labels[a],src=self.labels[src],dst=self.labels[dst],gateways=[dict(node=self.labels[b],weight=1.0)]) for a,b in zip(chain,chain[1:])])
            solver=dict(status='not_used',rule='Exact feasible simple chain, lexicographic tie break' if mode=='hops' else 'Operator-selected ordered simple chain')
        else:
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
            from planner import solve
            indices=[self.base['nodes'].index(x) for x in nodes]
            mean=[[self.base['mean'][i][j] for j in indices] for i in indices];variance=[[self.base['variance'][i][j] for j in indices] for i in indices]
            for i,a in enumerate(selected):
                for j,b in enumerate(selected):
                    if i!=j and (a,b) not in edges:mean[i][j]=0;variance[i][j]=1
            problem=dict(nodes=nodes,flows=[dict(src=self.labels[src],dst=self.labels[dst],rate=.05,qos=.9)],mean=mean,variance=variance,channel_provenance=dict(catalog=self.list_models()[0],selected_directed_edges=[list(e) for e in sorted(edges)],scope='Offline model preview, not current measured link graph'))
            answer=solve(problem)
            if answer['status']!='optimal':fail('solver_'+answer['status'],'SOCP did not yield a usable optimal table')
            update=answer['update']
            if any((self.back[r['node']],self.back[g['node']]) not in edges for r in update['routes'] for g in r['gateways']):fail('solver_forbidden_edge','solver retained a logically excluded edge, no probability post-edit')
            solver=dict(status=answer['status'],solver=answer['solver'],slack=answer['slack'],unit='dimensionless model rate',objective='maximize common robust margin, not minimum hops or measured latency')
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'bridge'))
        from bridge import quantize
        probabilities=[]
        for row in update['routes']:
            values=[g['weight'] for g in row['gateways']];quantized=quantize(values);total=sum(values)
            for g,w in zip(row['gateways'],quantized):
                probabilities.append(dict(src=self.back[row['node']],dst=self.back[g['node']],raw_weight=g['weight'],normalized_probability=g['weight']/total,encoded_weight=w,encoded_probability=w/65535,flow_src=src,flow_dst=dst))
        support={(e['src'],e['dst']) for e in probabilities if e['encoded_weight']>0}
        required=sorted(set(chain) if chain else self._reachable(src,dst,support)|{dst})
        reasons=[];live=live or {}
        if not live:reasons.append('hardware_status_unknown')
        if live.get('busy'):reasons.append('hardware_busy')
        ready=set(live.get('ready_nodes',[]))
        if not set(required)<=ready:reasons.append('required_nodes_not_ready')
        publisher=live.get('publisher');boot=live.get('publisher_boot')
        if publisher not in selected or publisher not in ready or type(boot)is not int or not 1<=boot<=0xffffffff:reasons.append('publisher_binding_unknown')
        if live.get('run_available')is not True:reasons.append('hardware_adapter_not_available')
        if not self._can_reach(src,dst,support):reasons.append('no_encoded_path')
        result=dict(ok=True,mode=mode,src=src,dst=dst,count=count,node_set=selected,bindings={k:self.labels[k] for k in selected},model=self.list_models()[0],solver=solver,
            selected_graph_edges=[dict(src=a,dst=b) for a,b in sorted(edges)],candidate_edges=probabilities,chain=chain,exact_hops=len(chain)-1 if chain else None,network_update=update,required_nodes=required,
            availability=dict(runnable=not reasons,reasons=reasons,publisher=publisher),
            semantics=dict(controlled=mode!='mid' or 'graph_edges'in q,probability_period_ms=500,per_packet_split=False,ttl_is_upper_bound_only=True,actual_path_source='device events, never preview inference',delivery_source='destination unique rx_local; link callback does not confirm destination',cycle_possible=mode=='mid',measured=False),
            notes=['No serial command encoded: H must recheck actual boot/version, allocate fresh seq and bridge.pack immediately before run','All model coefficients are assumptions from prior solved input; hardware availability is a separate current H observation'])
        canonical=json.dumps({k:result[k] for k in ('mode','src','dst','count','node_set','network_update')},sort_keys=True,separators=(',',':'))
        result['plan_fingerprint']=hashlib.sha256(canonical.encode()).hexdigest();return result

    @staticmethod
    def _reachable(src,dst,edges):
        seen={src};todo=[src]
        while todo:
            node=todo.pop()
            if node==dst:continue
            for a,b in edges:
                if a==node and b not in seen:seen.add(b);todo.append(b)
        return seen

    @classmethod
    def _can_reach(cls,src,dst,edges):return dst in cls._reachable(src,dst,edges)
