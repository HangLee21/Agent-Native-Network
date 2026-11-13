from available_plan import materialize as available
def materialize(package,assets,case,infos,run,labels):
 p=available(package,assets,case,infos,run,labels,participants='BC');p['flows']=[f for f in p['flows'] if f['source']==labels['B']];p['pilot']=True;p['scope']='Mixed-build UART transport validation B->C only, not official model or paired data.';return p
