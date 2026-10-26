import json,glob,collections,re,os,statistics,sys
S=sys.argv[1]
BREACH={"full","reqsupply","leak","subtotal","protected","rubber","unchecked"}
# load audits keyed by (model label, key)
aud={}
k2=json.load(open(S+"/k2_notes_audit.json"))
for f in glob.glob(S+"/audit_glimmer/out/*.jsonl")+glob.glob(S+"/audit_qwen/out/*.jsonl")+glob.glob(S+"/audit_ckpt/out/*.jsonl")+glob.glob(S+"/audit_gemma12/out/*.jsonl")+[S+"/audit_gemma12/auto.jsonl",S+"/audit_glimmer/auto.jsonl",S+"/audit_qwen/auto.jsonl",S+"/audit_ckpt/auto.jsonl"]:
    for l in open(f):
        if l.strip(): a=json.loads(l); aud[(a["model"],a["key"])]=a
import sys as _s; _s.path.insert(0,"analysis/scorer_only_2026-10"); from sv import sv as _sv
_LAB={"K2-Horizon-3.7B":"final_rcp","K2-Horizon-7B":"final7b_rcp","K2-Horizon-32B FP8":"fp8_32b_rcp","Muse-Glimmer-30B":"glimmer30b_rcp","Qwen3.8-27B":"qwen38_rcp","Gemma-4-12B":"gemma412b_rcp"}
for _t,_p in [("mid_4_10000","mid4"),("rl_merged","rlm"),("sft_1_10000","sft1"),("sft_2_2500","sft2")]:
    for _z,_q in [("7B","7b"),("3.7B","3b")]: _LAB[f"K2-{_z}-{_t}"]=f"ckpt{_q}_{_p}_rcp"
_V={}
for _lab,_pre in _LAB.items():
    for _g in ("records","pricing","exam","approvals"):
        _d=glob.glob(f"runs/rcp/{_pre}_bench_card_{_g}_full/*/")[0]; _f=_d+"results_rescored.jsonl" if os.path.exists(_d+"results_rescored.jsonl") else _d+"results.jsonl"
        for _l in open(_f):
            _r=json.loads(_l); _r["_game"]=_g; _V[(_lab,_r["episode_id"][:8])]=_sv(_r)["v"]
def verdict(model,key):
    return _V.get((model,key))

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
