"""Small KiCad S-expression reader/writer used by the recovered core tools."""
import json,re
class S(str):pass
def parse(text):
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()]+',text);i=0
    def read():
        nonlocal i
        tok=tokens[i];i+=1
        if tok=='(':
            result=[]
            while tokens[i]!=')':result.append(read())
            i+=1;return result
        return json.loads(tok) if tok.startswith('"') else S(tok)
    result=read();assert i==len(tokens),'Trailing S-expression tokens';return result
def dump(value,level=0):
    if isinstance(value,list):
        if any(isinstance(x,list) for x in value):return '('+'\n'.join(('\t'*(level+1) if i and isinstance(x,list) else '')+dump(x,level+1) for i,x in enumerate(value))+')'
        return '('+' '.join(dump(x,level+1) for x in value)+')'
    if isinstance(value,S):return value
    return json.dumps(value,ensure_ascii=False)
def children(value,key):return [x for x in value if isinstance(x,list) and x and x[0]==key]
def child(value,key):return next(iter(children(value,key)),None)
def prop(value,key):return next((x for x in children(value,'property') if x[1]==key),None)
CORE_REFS=['U1','L1','X1','R2','R3']+[f'C{i}' for i in [3,4,6,7,8,9,10,11,12,13,14,15,16,17,18,20]]
GROUP='WING27_OFFICIAL_RP2354_CORE'
