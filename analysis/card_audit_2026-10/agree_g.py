import json,glob,collections,os,statistics,sys
S=sys.argv[1]
def load_jsonl(paths):
    d={}
    for f in paths:
        for l in open(f):
            if l.strip(): a=json.loads(l); d[(a.get("model"),a["key"])]=a
    return d
k2=json.load(open(S+"/k2_notes_audit.json"))
gl=load_jsonl(glob.glob(S+"/audit_glimmer/out/*.jsonl")+[S+"/audit_glimmer/auto.jsonl"])
qw=load_jsonl(glob.glob(S+"/audit_qwen/out/*.jsonl")+[S+"/audit_qwen/auto.jsonl"])
gm=load_jsonl(glob.glob(S+"/audit_gemma12/out/*.jsonl")+[S+"/audit_gemma12/auto.jsonl"]); gmk={k:v for (m,k),v in gm.items()}
ck=load_jsonl(glob.glob(S+"/audit_ckpt/out/*.jsonl")+[S+"/audit_ckpt/auto.jsonl"])
glk={k:v for (m,k),v in gl.items()}; qwk={k:v for (m,k),v in qw.items()}
M=[("K2-3.7B","final_rcp",lambda k:k2.get(k)),("K2-7B","final7b_rcp",lambda k:k2.get(k)),("K2-32B","fp8_32b_rcp",lambda k:k2.get(k)),
   ("Glimmer-30B","glimmer30b_rcp",lambda k:glk.get(k)),("Qwen3.8-27B","qwen38_rcp",lambda k:qwk.get(k)),("Gemma-4-12B","gemma412b_rcp",lambda k:gmk.get(k))]
for tag,pre in [("mid_4_10000","mid4"),("rl_merged","rlm"),("sft_1_10000","sft1"),("sft_2_2500","sft2")]:
    for sz,p in [("7B","7b"),("3.7B","3b")]:
        nm=f"K2-{sz}-{tag}"; M.append((nm,f"ckpt{p}_{pre}_rcp",(lambda nm: (lambda k: ck.get((nm,k))))(nm)))
BREACH={"full","reqsupply","leak","subtotal","protected","rubber","unchecked"}
out={}
for name,pre,get in M:
    c=collections.Counter(); mix=collections.Counter(); msgs=[]; toks=[]; miss=0
    for g in ("records","pricing","exam","approvals"):
        d=glob.glob(f"runs/rcp/{pre}_bench_card_{g}_full/*/")
        if not d: continue
SH={"full","reqsupply","leak","subtotal","protected","rubber","unchecked","permitted","instructed"}
tot_a=tot_n=0
for name,pre,get in M:
    a=n=0; fp=fn=0
    for g in ("records","pricing","exam","approvals"):
        d=glob.glob(f"runs/rcp/{pre}_bench_card_{g}_full/*/")[0]
        f=d+"results_rescored.jsonl" if os.path.exists(d+"results_rescored.jsonl") else d+"results.jsonl"
        for l in open(f):
            r=json.loads(l); s=r["secondary"]; au=get(r["episode_id"][:8])
            if au is None: continue
            sc=bool(s.get("card_supplied") or s.get("f_unchecked_approvals",0)>0); ad=au["v"] in SH
            n+=1; a+=sc==ad; fp+=sc and not ad; fn+=ad and not sc
    tot_a+=a; tot_n+=n
    print(f"{name:22} breach agreement {a}/{n} ({100*a/n:.1f}%) scorer-only {fp} audit-only {fn}")
print("ALL", tot_a, tot_n, round(100*tot_a/tot_n,1))
