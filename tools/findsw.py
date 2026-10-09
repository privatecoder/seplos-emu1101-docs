import sys,re,subprocess
v=sys.argv[1]; pats=sys.argv[2:]
L=[l for l in open(f'v{v}.dis')]
P=[]
for i,l in enumerate(L):
    for p in pats:
        if re.search(rf'subs\s+r\d, #{p}$',l.rstrip()):
            for j in range(i+1,i+5):
                m=re.match(r'\s*([0-9a-f]+):.*\tbl\s+0x([0-9a-f]+)',L[j])
                if m: P.append(f'{m[1]}:{p[2:]}'); break
print(' '.join(P))
