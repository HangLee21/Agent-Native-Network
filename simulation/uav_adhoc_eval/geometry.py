"""Independent geometry metrics; input explicitly declares position units and radius."""
import math

def measure(positions,velocities,radius):
    ids=sorted(positions); adjacency={n:set() for n in ids};relative=[]
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            d=math.dist(positions[a],positions[b])
            relative.append(math.dist(velocities[a],velocities[b]))
            if d<=radius:adjacency[a].add(b);adjacency[b].add(a)
    remaining=set(ids);sizes=[];reachable=0
    while remaining:
        todo=[remaining.pop()];count=0
        while todo:
            n=todo.pop();count+=1
            for peer in adjacency[n]&remaining:remaining.remove(peer);todo.append(peer)
        sizes.append(count);reachable+=count*(count-1)
    n=len(ids)
    return dict(nodes=n,directed_reachable_pairs=reachable,directed_total_pairs=n*(n-1),
        largest_component=max(sizes,default=0),components=len(sizes),
        mean_pair_relative_speed_m_s=sum(relative)/len(relative) if relative else None,
        max_pair_relative_speed_m_s=max(relative,default=None),
        undirected_edges=sum(map(len,adjacency.values()))//2)
