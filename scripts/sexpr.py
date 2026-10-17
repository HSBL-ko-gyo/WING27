import re,json
class S(str): pass
def parse(t):
 toks=re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()]+',t); i=0
 def p():
  nonlocal i
  x=toks[i];i+=1
  if x=='(':
   a=[]
   while toks[i]!=')':a.append(p())
   i+=1;return a
  if x.startswith('"'):return json.loads(x)
  return S(x)
 return p()
def dump(a,level=0):
 if isinstance(a,list):
  if any(isinstance(x,list) for x in a):return '('+'\n'.join(('\t'*(level+1) if i and isinstance(x,list) else '')+dump(x,level+1) for i,x in enumerate(a))+')'
  return '('+' '.join(dump(x,level+1) for x in a)+')'
 if isinstance(a,S):return a
 return json.dumps(a,ensure_ascii=False)
def children(a,k):return [x for x in a if isinstance(x,list) and x and x[0]==k]
def child(a,k):return next(iter(children(a,k)),None)
def prop(a,k):return next((x for x in children(a,'property') if x[1]==k),None)
