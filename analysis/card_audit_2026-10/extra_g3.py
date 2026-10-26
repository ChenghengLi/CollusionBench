import json,glob,collections,re,os,statistics,sys
S=sys.argv[1]
BREACH={"full","reqsupply","leak","subtotal","protected","rubber","unchecked"}
# load audits keyed by (model label, key)
aud={}
k2=json.load(open(S+"/k2_notes_audit.json"))
for f in glob.glob(S+"/audit_glimmer/out/*.jsonl")+glob.glob(S+"/audit_qwen/out/*.jsonl")+glob.glob(S+"/audit_ckpt/out/*.jsonl")+glob.glob(S+"/audit_gemma12/out/*.jsonl")+[S+"/audit_gemma12/auto.jsonl",S+"/audit_glimmer/auto.jsonl",S+"/audit_qwen/auto.jsonl",S+"/audit_ckpt/auto.jsonl"]:
    for l in open(f):
        if l.strip(): a=json.loads(l); aud[(a["model"],a["key"])]=a
def verdict(model,key):
    a=aud.get((model,key)) or (k2.get(key) if model.startswith("K2-Horizon") else None)
    return a["v"] if a else None
# parse all packets
games=[]
for pdir in ["audit","audit_glimmer","audit_qwen","audit_ckpt","audit_gemma12"]:
    for f in sorted(glob.glob(f"{S}/{pdir}/packets/*.txt")):
        txt=open(f).read()
        for blk in txt.split("\n### ")[0:]:
            blk=blk.lstrip("# ").strip()
            if not blk: continue
            head=blk.split("\n")[0]
            m=re.match(r"([0-9a-f]{8}) \| ([^|]+) \| (\w+) (\w+) (\S+)",head)
            if not m: continue
            key,model,g,route,cond=m.group(1),m.group(2).strip(),m.group(3),m.group(4),m.group(5)
            units=re.search(r"units: ([^|\n]+)",head)
            task=blk.split("TASK-PHASE ITEMS:")[1].split("REPORT-PHASE ITEMS:")[0].split("FINAL REPORT:")[0] if "TASK-PHASE ITEMS:" in blk else ""
            lines=[l for l in task.split("\n") if l.startswith("[call")]
            games.append(dict(key=key,model=model,g=g,route=route,cond=cond,lines=lines,v=verdict(model,key)))
print("parsed games",len(games),"with verdict",sum(1 for x in games if x["v"]))
fam=lambda m: "Gemma" if "Gemma" in m else "Qwen" if "Qwen" in m else "Glimmer" if "Glimmer" in m else ("K2-7B ckpt" if "K2-7B-" in m else "K2-3.7B ckpt" if "K2-3.7B-" in m else "K2 final")

pol=collections.Counter(); ch=collections.Counter()
for x in games:
    if x["g"]=="approvals" or x["v"] not in BREACH: continue
    leaks=[i for i,l in enumerate(x["lines"]) if "LEAK" in l]
    F=fam(x["model"])
    if leaks:
        i=leaks[0]
        pol[(F,"n")]+=1
        pol[(F,"strict")]+= "policy" in " ".join(x["lines"][:i]).lower()
    if x["route"]=="blocked":
        ll=[l for l in x["lines"] if "LEAK" in l]
        ch[(F,"n")]+=1
        ch[(F,"forum")]+= any("→ forum" in l for l in ll)
        ch[(F,"dm")]+= any(re.search(r"→ (?!forum|file)",l) for l in ll)
for F in ["K2 final","K2-7B ckpt","K2-3.7B ckpt","Glimmer","Qwen","Gemma"]:
    print(F,"policy strictly before",pol[(F,"strict")],"/",pol[(F,"n")],"| blocked breach games",ch[(F,"n")],"forum",ch[(F,"forum")],"dm",ch[(F,"dm")])
tn=sum(ch[(F,"n")] for F in ["K2 final","K2-7B ckpt","K2-3.7B ckpt","Glimmer","Qwen"])
print("without Gemma", tn, sum(ch[(F,"forum")] for F in ["K2 final","K2-7B ckpt","K2-3.7B ckpt","Glimmer","Qwen"]), sum(ch[(F,"dm")] for F in ["K2 final","K2-7B ckpt","K2-3.7B ckpt","Glimmer","Qwen"]))
