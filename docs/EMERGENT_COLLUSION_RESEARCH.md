# Emergent collusion under a shared goal: literature notes and design implications

Chengheng Li Chen · CollusionGen · 10 October 2026 · compiled from five literature searches
(definitions; shared-goal rule-breaking; incentives and collusion theory; realistic workplace
environments; measurement and study design). Items marked *unverified* were not confirmed in the
source text.

## 1. Is joint rule-breaking under a shared goal "collusion"?

Yes, under the two most-cited AI definitions, provided the harmed party and the broken rule are
clear.

- **Hammond et al. 2025, *Multi-Agent Risks from Advanced AI*, §2.3** (arXiv 2502.14143):
  collusion is "unwanted cooperation between AI systems", typically "secretive cooperation ... at
  the expense of one or more other parties", often "in violation of some law, rule, or ethical
  standard". §2.3.1: collusion "may also arise when agents have complementary interests ... but
  where certain kinds of cooperation are undesirable – i.e., the agents are jointly misaligned."
  Explicit vs tacit collusion is distinguished by communication; intent "may be hard to ascribe".
- **Motwani et al., NeurIPS 2024, *Secret Collusion among AI Agents*** (arXiv 2402.07510):
  agents "coordinate their actions in ways that deviate from the system designer's intended rules
  ... at the expense of the system's integrity"; it "need not depend on intent". Secret collusion
  hides the interaction from oversight (steganography).
- **Fish, Gonczarowski & Shorrer, *Algorithmic Collusion by LLMs*** (arXiv 2404.00806):
  outcome-based (supracompetitive outcomes without design), no communication or intent needed.
- **Agrawal et al. 2025** (arXiv 2507.01413): "secretive cooperation that harms another party";
  communication channels increase it, oversight reduces it but profit pressure often wins.
- **Nakamura et al. 2026, *Colosseum*** (arXiv 2602.15198): collusion inside cooperative systems;
  direct, hidden (in actions only) and attempted ("collusion on paper", in talk only).
  *Wording from a page summary.*

**Conditions that separate collusion from helpfulness:** (1) two or more agents act jointly
(one agent oversharing alone is leakage, not collusion); (2) a party outside the coalition bears
the cost or a principal's rule is broken (here: the data owners and the confidentiality rule);
(3) often, but not necessarily, secrecy or evasion of oversight.

## 2. What empirical work shows

| Study | Setup | Key finding |
|---|---|---|
| Lynch et al. 2025, *Agentic Misalignment* (arXiv 2510.05179) | 16 models in a simulated company | under goal conflict every model leaked confidential documents some of the time; near-zero leaks without goal conflict; explicit bans reduced but did not remove it; 55% vs 6.5% blackmail when the model thought it was real vs a test |
| Li et al., ODCV-Bench (arXiv 2512.20798) | 40 scenarios, 12 models, KPI pressure | constraint violations 0–63% (v5); models judged their own actions unethical afterwards |
| MAGPIE (arXiv 2510.15186) | 200 collaborative tasks needing private data | closest design to ours: even with "do not share", leakage up to 51% (Gemini 2.5 Pro), 35% (GPT-5); explicit instructions cut leakage only 4–10 pp |
| Priyanshu et al. 2026 (arXiv 2605.27766) | multi-agent social simulation | 45% leakage multi-turn; agents 8× more likely to disclose after seeing a peer do it |
| **Shi, Zhang & Yang 2026, *Emergent Collusion in Long-Horizon LLM Agent Interaction*** (arXiv 2609.24967) | two agents cross-verifying under shared rewards | collusion in 94% of trajectories across 10 models; peer behaviour, history and reward structure drive it; limiting history reduces it. **Nearest neighbour: cite and differentiate.** |
| Paglieri et al. 2026 (DeepMind, arXiv 2609.04170) | 100-agent research swarm | an exploit spread through a shared library and DMs; other agents whistle-blew and boycotted. *Figures from a secondary summary.* |
| PrivacyLens, AgentDAM, ConfAIde | single-agent privacy | 9–57% leakage depending on model and prompt; probing answers do not predict actions |

## 3. Theory: what a shared goal should change

- **Shared payoffs raise group dishonesty** (Weisel & Shalvi 2015, *PNAS*: aligned payoffs gave
  far more collaborative lying than individual or partner-only payoffs; Wiltermuth 2011; Conrads
  et al. 2013: diffusion of responsibility under team pay).
- **Communication matters more than payoff commonality** (Kocher, Schudy & Spantig 2018: groups
  lie more because of within-group discussion). Leib et al. 2021 meta-analysis: collaborative
  dishonesty rises with incentives and falls when third parties are visibly harmed.
- **Group size**: tacit collusion collapses beyond 2–3 firms (Huck, Normann & Oechssler 2004,
  "Two are few and four are many"); communication helps most at medium size (Fonseca & Normann
  2012). But the chance that *someone* leaks grows like 1 − (1 − p)^N.
- **Algorithmic collusion** arises without communication (Calvano et al. 2020, *AER*), less as N
  grows (*exact numbers unverified*).

**Predictions for our shared-goal design** (to test):
1. Leaking rises under a shared goal, but channels matter more than the payoff (2×2: individual vs
   shared goal × forum/DMs on vs off).
2. Dumping replaces negotiation: fewer trades and quid-pro-quo, more bulk posting "for the team".
3. Cascades: the hazard of further leaks jumps after the first leak, more after a public one.
4. Group size splits: P(any leak) rises with N; fully coordinated all-agent pooling peaks around
   N = 4 and falls at 6; one objecting agent may suppress leaking.
5. Monitoring moves leaks rather than stopping them (announced monitoring of the forum shifts
   leaks to DMs, paraphrase or encoding); expect "collusion on paper".
6. Visible harm to data owners reduces leaking; higher team stakes increase it.

## 4. Realism: what makes workplace environments credible

Benchmarks: TheAgentCompany (arXiv 2412.14161), WorkArena++ (NeurIPS 2024), CRMArena-Pro
("near-zero confidentiality awareness"), τ/τ²-bench (policy documents, state-based grading),
AppWorld (arXiv 2407.18901), EnterpriseBench (arXiv 2510.27287), DRBench (arXiv 2510.00172:
ground-truth and decoy facts in mixed documents), DABstep (exact factoid grading over messy data),
HiddenBench (arXiv 2505.11556: accuracy falls from 81% to 30% when information is split).

Realism features, each with a documented rule so the answer stays exact: correction rows that
override earlier ones; voided duplicates; inconsistent ids with a crosswalk; mixed formats; file
versions where only approved ones count; policy changes mid-period; memo threads where one is
signed off; decoy records; procedures in the knowledge base rather than the prompt; facts only in
a teammate's notes; an unanswerable variant; structured answers; leak detection via planted
canary values. Recipe: generate a clean ground truth, apply mess with documented undo rules,
verify a reference solver on the messy files reproduces the gold answer.

## 5. Measurement and study design

- **Detection**: three tiers as in AgentLeak (arXiv 2602.11510): exact canary matching (high
  precision, low recall: models paraphrase), structured-field matching, and a calibrated LLM judge
  for derived facts; report leaks per channel (inter-agent messages leak far more than outputs).
  Separate needed from gratuitous disclosure against an oracle's minimal set (MAGPIE, AgentLeak).
- **Collusion markers** (human-validated LLM judge, report κ): explicit agreements to bypass the
  rule, rationalisations ("derived facts, nothing raw"), moving to private channels; requested vs
  volunteered leaks; turn of first leak; refusals and whistle-blowing.
- **Controls**: C0 shared goal + rule (main); C1 shared goal, no rule (ceiling); C2 explicit
  permission to share what the task needs; C3 individual goals + rule (our ring design: C0 vs C3
  is the causal test of "shared goal"); C4 strict rule with penalties; scripted oracle and
  scripted honest/leaking peer (contagion).
- **Validity check**: each scenario should also be solvable without breaking the rule (for
  example through yes/no queries or aggregates), otherwise leaking is simply necessary.
- **Statistics**: paired designs on the same scenarios and seeds; Wilson or Bayesian intervals at
  small n (Bowyer et al., arXiv 2503.01747); clustered errors by scenario (Miller, arXiv
  2411.00640); mixed-effects logistic models; consider pre-registration (OSF).
- **Size** (suggested): 10 scenarios × 5 seeds = 50 games per cell; C0, C1, C3 on 6 models and
  C2, C4 on 3 models ≈ 1,200 games; ±14 pp at n = 50, detecting ~25–30 pp differences.

## 6. What this means for the next round

1. Keep the confidentiality rule issued by a principal separate from the team (the organisation's
   data policy), so breaking it is not "doing what the boss wants".
2. Code joint breaches (one asks, another supplies; agreed use of the shared folder) separately
   from unilateral oversharing.
3. Run the shared-goal games (C0) against the ring games (C3) on the same models, plus a
   no-rule ceiling (C1) and an explicit-permission control (C2).
4. Log first leak, cascades, channel, framing, refusals and whistle-blowing.
