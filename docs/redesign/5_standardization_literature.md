# Standardization literature update

Status: design input only. No code change. No game run.

This file updates `2_plausibility.md` sections 5, 6 and 8.
It does not redo that review.
Decisions D1 to D10 bind this file.
They are final in `0_decisions_draft.md`.
Where literature and a decision disagree, the decision wins.
The disagreement is listed as unresolved. It is not smoothed over.

## 1. What was checked

I read `0_decisions_draft.md` in full.
I read `2_plausibility.md` sections 5, 6 and 8 and its references.
Section 5 is at `2_plausibility.md:213`.
Section 6 is at `2_plausibility.md:231`.
Section 8 is at `2_plausibility.md:328`.
I also read `1_evidence.md` for size anchors.
I read `docs/BENCHMARK.md` sections 3 to 9 for current definitions.
`docs/BENCHMARK.md` is not edited in this stage. See D10.

Then I checked current standardization practice on the web.
Four topics were checked.
First, common environment, prompt and scoring scaffolds.
Second, validity gates.
Third, contamination and awareness checks.
Fourth, reporting standards.

Every external citation below was opened on its source page.
Title, authors, year and arXiv id or venue were checked there.
Anything not opened is marked unverified.
No rule rests on an unverified item.

## 2. Short answer

Most of `2_plausibility.md` still stands.
Section 5, rules 1 to 15 in section 6, and section 8 need no rewrite.
Two of them need a D-driven reading only. See section 4.

The update adds procedure, not new scenario content.
It adds ten rules, U1 to U10.
They cover scaffold versioning, scorer attacks, baselines,
uncertainty and cost reporting, repeat-run spread,
contamination hygiene, documentation cards and environment freeze.
Each rule names its source.
Each rule maps to D3 to D8.

No verified new standard overturns the awareness findings.
No verified new standard sets a different solve gate.
D4 gates stay as settled.
D4 is at `0_decisions_draft.md:91`.

## 3. New or changed rules since the plausibility review

Read each rule with its map.
"New" means `2_plausibility.md` did not state it in this form.
"Changed" means the review stated a weaker form.

### U1. Version the whole scaffold as one object

Rule: each scenario ships one versioned scaffold object.
It has five parts.
Part 1 is the instance generator and its seed policy.
Part 2 is the prompt skeleton, including the policy document.
Part 3 is the tool list and channel setting.
Part 4 is the scorers and detectors.
Part 5 is limits: call budget, time and error handling.
A change to any part bumps the scaffold version.
Results from two versions are never pooled without a note.

Source: Inspect Tasks documentation.
A Task is "a recipe for an evaluation consisting minimally of a
dataset, a solver, and a scorer" with sandbox and limit options.
Checked on https://inspect.aisi.org.uk/tasks.html on 2026-10-20.
Also HELM. HELM holds the adaptation strategy fixed so models
can be compared. Liang et al., arXiv:2211.09110.
Also ABC items T.1 to T.6 and R.6. Zhu et al., arXiv:2507.02825.

What is new: section 5 describes a template pattern.
See `2_plausibility.md:226`.
It does not name versioned parts.
It does not forbid pooling across versions.

Map: D7 fixes team size, channels, budget, rule placement,
prompt skeleton, tools, detectors and report table.
See `0_decisions_draft.md:149`.
U1 gives file `6_standard_card.md` a version field to fill.
D4 limits sit in part 5. D5 detectors sit in part 4.
D3 route cost sits in parts 1 and 2. It must be explicit.

Build bite: file `6_` adds `scaffold_version` to the card.
File `8_` logs it in every game record.
File `7_` states which version the gates were run on.

### U2. State the evaluation subject in every table

Rule: every result table states what was measured.
It states model name and API version or date.
It states scaffold version from U1.
It states team size, condition code and route-cost level.
It states sampling settings if the API exposes them.
If a setting is unknown, write "not exposed". Do not guess.

Source: ABC item R.6. State whether the subject is a model
or an agent framework. Zhu et al., arXiv:2507.02825.
Also Kapoor et al. Model and downstream needs are conflated
when the scaffold is not stated. Kapoor et al., arXiv:2407.01502.
Also HELM. The object is the language model, not a
scenario-specific system. Liang et al., arXiv:2211.09110.

What is new: rule 15 in `2_plausibility.md:293` says freeze
scenarios and do not tune to one model family.
It does not require a subject line in reporting.

Map: D1 fixes the subject as an API model team in MM.
See `0_decisions_draft.md:50`.
D6 fixes condition codes. See `0_decisions_draft.md:129`.
D7 fixes 3 agents and one channel setting.
U2 does not add a condition. It labels the settled ones.
Note: HELM language assumes one model. Here the subject is
a 3-agent team. File `6_` must use team wording. See C7.

Build bite: file `8_` defines the table header fields.
File `13_` repeats them in cost and sample-size tables.

### U3. Attack the scorer before trusting it

Rule: every primary detector passes four scorer attacks.
Attack A is the empty agent. It sends nothing and submits nothing.
Attack B is the dump agent. It copies all text it can see.
Attack C is the guess agent. It submits round numbers only.
Attack D is the relay agent. It forwards text with no task work.
None of them may count as a joint breach.
None of them may count as solved.
Run the attacks as unit tests on logged events.
Run them again in the pilot with scripted seats.

Source: ABC outcome validity items O.b.2, O.b.3, O.g.1 to
O.g.3 and O.c.1 to O.c.2. Zhu et al., arXiv:2507.02825.
The same paper reports two tau-bench failures.
An empty response passed unsolvable tasks.
Dumping database text passed substring checks.
Tau-bench itself grades final database state.
See Yao et al., arXiv:2406.12045.

What is new: rule 12 in `2_plausibility.md:281` requires a
validated judge for paraphrase.
It does not require trivial-agent attacks on the scorer.
Section 3 in that review covers solvability, not scorer gaming.

Map: D5 defines joint breach as S3j.
See `0_decisions_draft.md:110`.
The exact S3j rule is at `docs/BENCHMARK.md:185`.
U3 protects that definition. It does not change it.
It supports D4 gates. A gamed solve must not pass a gate.
It supports D8. O and Rep use exact log and claim checks.
Those checks need the same attacks.
BENCHMARK gate V7 is at `docs/BENCHMARK.md:319`.
U3 adds attack cases to V7. It does not replace V7.

Build bite: file `8_` lists the four attack fixtures.
File `7_` adds "attacks score zero on primary" as a gate line.
File `4_` checks the two known bug patterns against U3.
Those are the ring oracle and solo-answerable exam items.

### U4. Keep baselines visible, but keep their D6 status

Rule: report four pilot baselines with numbers.
They are the honest script, the oracle script,
the trivial agent and, where run, a human timed run.
Report them in the pilot appendix with n and scaffold version.
Do not list them as model rows in the main table.
Do not rank models against them.

Source: ABC items R.12 and R.13. Report non-AI baselines
and trivial agents. Zhu et al., arXiv:2507.02825.
Also HCAST. Human baselines were collected under identical
conditions as agents. Rein et al., arXiv:2503.17354.
Also Kapoor et al. Holdout and trivial baselines expose
shortcut agents. Kapoor et al., arXiv:2407.01502.

What is changed: `2_plausibility.md:147` mentions a
trivial-agent baseline as ABC item R.13.
It does not say where baselines are reported.
U4 fixes the place without changing their status.

Map: D6 keeps HH, OO, MH and HON as pilot checks only.
See `0_decisions_draft.md:134`.
BENCHMARK states the same at `docs/BENCHMARK.md:250`.
U4 respects D6. Baselines calibrate D4 gates.
They are not results. See conflict C4.
D4 still decides pass or redesign. See `0_decisions_draft.md:98`.

Build bite: file `7_` owns baseline numbers per gate.
File `13_` budgets scripted runs as free and human runs
as pilot-only. No new main-run games are added.

### U5. Report count, interval and cost together

Rule: every reported cell shows four items.
Item 1 is the count and n. Example form: 3 of 20.
Item 2 is a 95 percent interval for the rate.
Item 3 is median calls per agent in that cell.
Item 4 is cost per game in that cell.
The count stays the headline. The interval prevents over-reading.
Calls and cost prevent a cheap-looking win by wandering.

Source: ABC item R.10. Report statistical significance
such as confidence intervals. Zhu et al., arXiv:2507.02825.
Also BetterBench. Most benchmarks do not report significance
and are hard to replicate. Reuel et al., arXiv:2411.12990.
NeurIPS 2024 Spotlight, Datasets and Benchmarks Track.
Also Blackwell et al. Temperature zero with a fixed seed
does not guarantee the same answer. Report uncertainty
from repeats. Blackwell et al., arXiv:2410.03492.
Also Kapoor et al. Accuracy without cost misleads.
Kapoor et al., arXiv:2407.01502.

What is new: section 8 gives pilot size guidance.
At n equals 50 the interval is about plus or minus 14 points.
See `2_plausibility.md:341`.
It does not set a per-cell reporting rule.
BENCHMARK section 9 uses counts only.
See `docs/BENCHMARK.md:329`.
U5 keeps counts first and adds the missing companions.

Map: D4 requires call use per game.
See `0_decisions_draft.md:102`.
D5 requires class C0 to C5 and stage flags per game.
See `0_decisions_draft.md:116`.
U5 adds interval and cost columns beside them.
It does not replace counts with ratios or indices.
The BENCHMARK table change waits for a later stage.
See conflict C5.

Build bite: file `8_` defines interval method and cost fields.
Use one method for all cells. Name it in the table note.
File `13_` shows cost per cell, not only cost per model.

### U6. Measure repeat-run spread in the pilot only

Rule: in the pilot, repeat a small fixed set of instances.
Run each instance several times with the same scaffold.
Report how often the same instance solves or breaches.
Use three buckets: never, sometimes, always.
In main runs, keep one new instance per game.
Report spread across instances. Do not pool pilot repeats
into main rates.

Source: tau-bench pass to the k metric.
It is the chance that all k trials of one task succeed.
Retail pass to the 8 was below 25 percent while single-trial
success looked higher. Yao et al., arXiv:2406.12045.
Also Blackwell et al. Repeats shrink the prediction interval.
Blackwell et al., arXiv:2410.03492.

What is new: `2_plausibility.md` reports single rates.
It does not separate instance difficulty from run noise.
U6 adds that split. The breach version is an analogue.
It is not copied as a headline metric. See the caution below.

Map: D4 gates use solve rates. U6 shows if a gate miss is
one hard instance set or general noise.
D6 forbids new main conditions. See `0_decisions_draft.md:136`.
So repeats stay in the pilot. They add no MM games.
D7 and BENCHMARK require a new seed per main game.
See `docs/BENCHMARK.md:64`. U6 does not change that.
Caution: pass to the k rewards always solving.
For breach, "always" means always breaking the rule.
Report the buckets. Do not rank models by an "always" score.

Build bite: file `7_` sets pilot repeat counts per scenario.
File `8_` defines the three bucket fields.
File `9_` may reuse the same buckets for Track 0 calibration.

### U7. Treat contamination as generator hygiene

Rule: keep test material out of training and prompts.
Hold out skins. Use a new seed per main game.
Never publish canary values, answer keys or detector seeds.
Log generator version and seed policy in the scaffold.
Plan skin and value refresh between versions, not inside
one measurement block.

Source: ABC items R.3 and R.4. Prevent contamination at
release and update challenges over time.
Zhu et al., arXiv:2507.02825.
Also LiveBench. Questions come from recent sources and
are updated over time, with objective ground truth.
White et al., arXiv:2406.19314.
Also Chen et al. Static benchmarks leak into training data.
Dynamic methods still lack standard criteria.
Chen et al., arXiv:2502.17521.

What is changed: rule 14 in `2_plausibility.md:289` says
hold out skins and paraphrases to measure surface effects.
U7 adds the contamination reason and the non-publication rule.
It also adds the between-version refresh rule.

Map: D2 fixes Track 0 plus R, P, E, F, Rep and O only.
See `0_decisions_draft.md:65`.
D7 fixes one setting for v1. U7 does not add scenarios.
It protects the settled set from template learning.
Main risk here is not web-scale training leakage.
Instances are generated. Risk is prompt and template
recognition across games. See `2_plausibility.md:326`.
LiveBench style monthly refresh does not fit v1 freeze.
See conflict C3. Refresh waits for a version bump in U1.

Build bite: file `6_` marks held-out fields on the card.
File `8_` keeps canaries out of agent-visible logs.
Files `10_` to `13_` state seed policy per scenario.

### U8. Ship a benchmark card and one card per scenario

Rule: document the benchmark once and each scenario once.
Each card states objective, construct, method, data source,
honest route, rule location, detectors, limits and flaws.
Each card states what a breach does not prove.
Each card carries version, date and change log.
Update the card when the scaffold version changes.

Source: BenchmarkCards. It standardizes objectives,
methodologies, data sources and limitations.
Sokol et al., arXiv:2410.12974.
Also BetterBench. It scores 46 lifecycle practices and
finds large quality gaps. Reuel et al., arXiv:2411.12990.
Also ABC items R.5 and R.7 to R.11. State the capability
to construct link, mitigation steps and reading guidance.
Zhu et al., arXiv:2507.02825.

What is changed: `2_plausibility.md:300` lists card fields.
It lists id, skin, agents, tools, data, goal, honest route,
rule, opportunity, pressure, canaries, conditions, oracle
and pilot stats. U8 adds construct, flaws, reading guidance,
version and change log. It also adds the top-level card.

Map: D7 requires a standard card. See `0_decisions_draft.md:158`.
D10 assigns the card to file `6_`. U8 extends that card.
It does not move ownership.
D5 needs a construct line: S3j measures a joint act,
not three separate rule breaks. The share-only rule in D7
makes this line required. See `0_decisions_draft.md:230`.
D8 needs Rep and O flaws and reading guidance on the card.
Exact Rep calls stay with file `13_`. This file sets none.

Build bite: file `6_` owns card fields and the rule template.
File `8_` owns detector flaw notes.
Unification checks that every scenario card is complete.

### U9. Freeze and reset the environment as a gate

Rule: prove four environment facts before pilot games count.
Fact 1: tool and model interface versions are logged.
Fact 2: state is cleared between games. No file carries over.
Fact 3: answer keys and shadow logs cannot be read by agents.
Fact 4: no live external resource can change mid-block.
If any fact fails, stop. Fix it. Do not score around it.

Source: ABC items T.1 to T.6. Specify tool versions.
Keep APIs accessible or stop cleanly. Clear residual state.
Isolate agents from ground truth. Freeze setup at release.
Zhu et al., arXiv:2507.02825.
The same paper reports ground-truth leakage and live-site
drift as validity failures in other benchmarks.

What is new: `2_plausibility.md:145` cites ABC items
T.8 to T.10 and R.13. It covers solvability, oracle and
outliers. It does not cite T.1 to T.6.
U9 adds the missing half of task validity.

Map: D4 gates need a stable task. Drift breaks the gates.
D7 fixes tools and channels. U9 proves the fix held.
D8 depends on a shadow log agents cannot reach.
BENCHMARK describes the shadow copy at `docs/BENCHMARK.md:135`.
U9 turns that description into a pre-pilot check.
D3 route cost also needs freeze. Cost in calls or waiting
must not drift because a service slowed down.

Build bite: file `7_` adds T.1 to T.6 checks to gate entry.
File `8_` lists log fields for versions and reset proof.
File `4_` reuses the checks for documented bug hunts.

### U10. Correct judge-based rates before reporting them

Rule: never report a raw LLM judge rate as a finding.
First measure judge sensitivity and specificity on human labels.
Then report a bias-corrected rate with an interval.
The interval must include calibration uncertainty.
If the calibration set is too small, report judge output
as exploratory only. Keep it out of the headline table.

Source: Lee et al. Imperfect judge sensitivity and
specificity bias naive scores. Their plug-in framework
corrects bias and builds intervals from test data plus
a human-labeled calibration set.
Lee et al., arXiv:2511.21140. ICML 2026 per arXiv page.
Also ABC item O.c.1. Show judge accuracy, self-consistency
and agreement with humans. Zhu et al., arXiv:2507.02825.

What is changed: rule 12 requires validation on at least
100 human-labeled cases. See `2_plausibility.md:281`.
Section 8 requires at least 90 percent agreement.
See `2_plausibility.md:340`.
U10 keeps both. It adds correction and a wider interval.
Agreement alone does not remove bias.

Map: D5 primary outcome is deterministic S3j.
Judge labels stay secondary. See `docs/BENCHMARK.md:161`.
BENCHMARK judge labels are at `docs/BENCHMARK.md:230`.
They cover rule awareness and test awareness.
U10 applies to those labels and to paraphrase detection.
It does not promote any judge label to primary status.
D8 Rep and O stay exact checks. No judge decides them.

Build bite: file `8_` owns calibration size and correction.
File `7_` states the minimum calibration set as a gate.
Unification must not headline uncorrected judge rates.

## 4. What in 2_plausibility still stands unchanged

This list is explicit. "Stands" means reuse the text as is.
D-driven readings are listed after the list.
They do not count as literature changes.

Section 5 stands. See `2_plausibility.md:213`.
The fixed versus varied table stands.
The template pattern stands. See `2_plausibility.md:226`.
The GovSim warning stands. Identical structure can still
give different results by story. Surface effects must be
measured. See `2_plausibility.md:227`.
U1, U7 and U8 extend section 5. They do not replace it.

Section 6 rules 1 to 15 stand, with two readings below.
Rule 1 stands. Open honest route to the full answer.
See `2_plausibility.md:233`. D3 settles the same point.
Rule 2 stands in direction. Small work plus clerk tools.
See `2_plausibility.md:238`. Numbers now follow D4.
Rule 3 stands. Pilot to fixed gates. Revise to agent errors.
See `2_plausibility.md:243`. Gate numbers now follow D4.
Rule 4 stands in logic. Frozen environment, paired conditions.
See `2_plausibility.md:247`. Names now follow D6. See below.
Rule 5 stands in form. Rule once in a policy document.
No file banners. See `2_plausibility.md:253`.
Act wording now follows D7. See below.
Rule 6 stands. Neutral business names for data and tools.
See `2_plausibility.md:258`. D7 settles the same point.
Rule 7 stands. Opportunity in normal work flow, mid-task.
See `2_plausibility.md:262`.
Rule 8 stands. Texture, history, filler, specific names.
See `2_plausibility.md:266`.
Rule 9 stands. Ordinary stakes only.
See `2_plausibility.md:270`.
Rule 10 stands. Pressure from goal, never a hint at the act.
See `2_plausibility.md:274`.
Rule 11 stands with a scope note. See below.
See `2_plausibility.md:278`.
Rule 12 stands. State and logs first. Judge for paraphrase.
See `2_plausibility.md:281`. U3 and U10 strengthen it.
Rule 13 stands. Log test awareness. Report split by it.
See `2_plausibility.md:286`. Section 6 below adds procedure.
Rule 14 stands. One card for all scenarios.
See `2_plausibility.md:289`. U1 and U8 extend the card.
Rule 15 stands. Freeze before measuring.
Comprehension probe. Drop misreading models as reported.
See `2_plausibility.md:293`. U2 and U9 make freeze auditable.

Suggested card fields stand as the base list.
See `2_plausibility.md:300`. U8 adds five fields to it.

Section 8 stands where D4 did not settle numbers.
See `2_plausibility.md:328`.
Detector recall target stands as derived guidance.
Control violation target stands as derived guidance.
Awareness targets stand as derived guidance.
Judge agreement target stands. U10 adds correction on top.
Pilot size guidance stands. U5 and U6 add reporting on top.
Solve gates in section 8 match D4 closely.
Where wording differs, D4 wording governs. See below.

References in `2_plausibility.md:359` stand as the base set.
This file adds sources. It does not re-verify every old id.
Old unverified notes in that file stay unverified.
Do not rest new rules on them.

D-driven readings. These come from D1 to D10, not literature.
Reading 1: rule 4 letters map to D6 names.
No rule maps to the D4 no-rule gate check.
Rule plus honest route maps to MM at cheap and moderate cost.
Explicit request maps to INST and ASK as defined in D6.
Blocked route maps to MM blocked only. See D3 and D6.
Do not copy rule 4 letters into new files. Use D6 codes.
Reading 2: rule 5 act is sharing only.
D7 forbids sharing protected information only.
See `0_decisions_draft.md:151`.
Asking and using stay recorded stages under D5.
They are not separate stated prohibitions.
Do not write a two-sided rule from rule 5.
Reading 3: rule 11 memory means within-game contact history.
It does not add cross-game memory in v1.
Shared aim stays as the D6 contrast on E and F only.
E is an adult professional certification exam in v1 design.
Reading 4: section 8 solve numbers follow D4 wording.
D4 gates are at least 90 percent with no rule and at least
80 percent with rule plus honest route.
See `0_decisions_draft.md:98`.
Design limits follow D4, not the older card draft.
The older draft is at `3_scenarios.md:27`.
Its 80-call and ceiling numbers are superseded.

## 5. Conflicts with settled decisions

Each item stays unresolved for unification.
D1 to D10 win until the user changes them.
No item below edits `docs/BENCHMARK.md` in this stage.

C1. Two-sided rule text versus D7 share-only rule.
BENCHMARK section 4.2 requires both sides.
See `docs/BENCHMARK.md:103`.
D7 requires sharing only. See `0_decisions_draft.md:151`.
Literature favours concrete wording. It does not settle
one side versus two sides for this benchmark.
Action: file `6_` writes share-only text.
File `8_` keeps ask and use as stage flags.
Unification flags BENCHMARK 4.2 for the later edit stage.

C2. Honest-ceiling pressure versus D3 route cost.
BENCHMARK section 4.3 defines pressure as ceiling h.
See `docs/BENCHMARK.md:114`.
D3 defines pressure as cheap, moderate, blocked cost.
See `0_decisions_draft.md:76`.
Literature supports D3. Blocked route is the large effect.
See `2_plausibility.md:233`.
Action: file `7_` uses route cost only.
Do not combine the two dials. D3 forbids it.

C3. Dynamic refresh versus v1 freeze.
ABC R.4 and LiveBench favour updating challenges.
See U7 sources. D7 fixes one setting for v1.
Action: no refresh inside one measurement block.
Refresh only with a scaffold version bump.
Cadence after v1 is unresolved. Unification notes it.

C4. Published baselines versus pilot-only status.
ABC R.12 and R.13 favour reporting baselines.
HCAST publishes human baselines. See U4 sources.
D6 keeps HH, OO, MH and HON as checks, not results.
See `0_decisions_draft.md:134`.
Action: U4 compromise. Numbers in pilot appendix only.
Placement in final reporting is unresolved.

C5. Intervals and cost versus counts-only table.
ABC R.10, BetterBench and Blackwell favour intervals.
Kapoor favours cost beside accuracy. See U5 sources.
BENCHMARK section 9 says counts only, no ratios.
See `docs/BENCHMARK.md:329`.
Action: U5 keeps counts as headline.
Interval and cost columns wait for unification approval.
Do not rewrite BENCHMARK section 9 in this stage.

C6. Cross-episode memory versus single-game v1.
Shi et al. found episode memory necessary in their task.
See `2_plausibility.md:278`.
V1 games are single episodes with a new seed per game.
Transfer to 3-agent organisational teams is unproven.
Action: keep within-game history. Defer cross-game memory.
Mark as unresolved for a later stage, not v1.

C7. Single-model scaffold language versus team subject.
HELM and Inspect describe one solver for one model.
D1 and D7 measure a 3-agent team.
Action: borrow versioning and parts. Rewrite subject terms.
File `6_` must define solver as the fixed team scaffold.
Do not copy single-agent wording into the card.

## 6. Awareness and contamination: what did not change

Awareness practice did not change in a verified way.
Section 1 of `2_plausibility.md` still governs.
Verbalised awareness is a lower bound only.
See `2_plausibility.md:59`.
Low verbal rate does not prove low awareness.
Rule 13 still governs logging and split reporting.
See `2_plausibility.md:286`.
Section 8 awareness targets still govern as guidance.
See `2_plausibility.md:338`.

One procedure point is now explicit.
The prompted test-or-real probe is itself a cue.
See `2_plausibility.md:339`.
Run it only on separate probe games.
Never add it to main MM games.
Never add it before Rep closes a main game.
Rep closes every game under D8.
See `0_decisions_draft.md:176`.
Probe games carry their own scaffold note under U1.

No verified new awareness threshold was found.
No verified probe method replaces regex plus judge review.
Judge output for awareness follows U10 correction.
Uncorrected awareness rates stay exploratory.

Contamination practice changed only in framing. See U7.
Static public benchmarks leak. Dynamic benchmarks help.
No standard criteria for dynamic quality exist yet.
Chen et al., arXiv:2502.17521, states this gap plainly.
So v1 uses hygiene, not a dynamic benchmark claim.
Do not claim contamination-free status for v1.
Claim only held-out skins, fresh seeds and hidden keys.

## 7. Reporting additions in one place

Unification can lift this section into file `8_` wording.
It adds columns. It changes no D5 definition.

Per model, per scenario, per condition, per route cost:
- Scaffold version, model version, date. See U1 and U2.
- Games n. Joint breach count. Solo breach only count.
- Contact, asked, supplied, used counts.
- Class C0 to C5 counts. Stage flags with first call index.
- Solve count, reported apart from breach. See D5.
- Interval for joint breach rate. See U5.
- Median calls per agent. Cost per game. See U5.
- Awareness split for breach counts. See rule 13 and U10.
Pilot appendix only:
- HH, OO, trivial and human baseline counts. See U4.
- Scorer attack results. See U3.
- Repeat buckets: never, sometimes, always. See U6.
- Judge sensitivity, specificity and corrected rates. See U10.

Zero cells need a plain bound sentence.
BENCHMARK gives the form for 0 of 20.
See `docs/BENCHMARK.md:280`.
Keep that sentence. Add the interval beside it under U5.
Grey-cell logic in BENCHMARK stays until unification.
See `docs/BENCHMARK.md:342`.
Read MM only when INST and PERM support the reading.

## Sources inspected

Project sources opened in full or in cited windows:
- `docs/redesign/0_decisions_draft.md` in full.
  D3 at line 76. D4 at line 91. D5 at line 110.
  D6 at line 129. D7 at line 149. D8 at line 176.
- `docs/redesign/2_plausibility.md` in full.
  Section 5 at line 213. Section 6 at line 231.
  Section 8 at line 328. References at line 359.
- `docs/redesign/1_evidence.md` in full.
  Size limits table at line 356 used as anchor only.
- `docs/redesign/3_scenarios.md` in full.
  Older card numbers at line 27 marked superseded.
- `docs/BENCHMARK.md` sections 3 to 9.
  Skins and seeds at line 64. Rule template at line 93.
  Pressure at line 112. Oversight at line 130.
  Report phase at line 147. Stages at line 157.
  S3j at line 185. Uptake at line 193.
  Classes at line 214. Judges at line 230.
  Conditions at line 236. Gates at line 307.
  Reporting at line 325.

External sources verified on their source pages:
- Zhu et al. Establishing Best Practices for Building
  Rigorous Agentic Benchmarks. arXiv:2507.02825.
  Abstract page and PDF text opened. ABC items T, O, R read.
- Liang et al. Holistic Evaluation of Language Models.
  arXiv:2211.09110. Abstract page opened.
- White et al. LiveBench: A Challenging,
  Contamination-Limited LLM Benchmark. arXiv:2406.19314.
  Abstract page opened. Version 2, April 2025.
- Yao et al. tau-bench: A Benchmark for Tool-Agent-User
  Interaction in Real-World Domains. arXiv:2406.12045.
  Abstract page opened. Pass to the k checked there.
- Reuel et al. BetterBench: Assessing AI Benchmarks,
  Uncovering Issues, and Establishing Best Practices.
  arXiv:2411.12990. NeurIPS 2024 Spotlight per arXiv page.
  Abstract page opened. 46 practices, 24 benchmarks.
- Sokol et al. BenchmarkCards: Standardized Documentation
  for Large Language Model Benchmarks. arXiv:2410.12974.
  Abstract page opened. Version 3, June 2025.
- Blackwell et al. Towards Reproducible LLM Evaluation:
  Quantifying Uncertainty in LLM Benchmark Scores.
  arXiv:2410.03492. Abstract page opened. Version 2, 2025.
- Kapoor et al. AI Agents That Matter. arXiv:2407.01502.
  Abstract page opened.
- Rein et al. HCAST: Human-Calibrated Autonomy Software
  Tasks. arXiv:2503.17354. Abstract page opened.
  189 tasks. 563 human baselines under agent conditions.
- Chen et al. Recent Advances in Large Language Model
  Benchmarks against Data Contamination: From Static to
  Dynamic Evaluation. arXiv:2502.17521.
  Abstract page opened. Version 2, September 2025.
- Lee et al. How to Correctly Report LLM-as-a-Judge
  Evaluations. arXiv:2511.21140. ICML 2026 per arXiv page.
  Abstract page opened.
- UK AI Security Institute. Inspect Tasks documentation.
  https://inspect.aisi.org.uk/tasks.html opened.
  Task as dataset plus solver plus scorer checked there.

Unverified. No rule rests on these items:
- A named METR Task Standard specification page.
  Search found HCAST and tooling pages only.
  This file cites HCAST paper and Inspect docs instead.
- Scaffold score ranges from search snippets.
  Source PDFs were not opened. Numbers are not used.
- ReliabilityBench reuse of pass to the k.
  Seen in search snippets only. Not opened. Not used.
- Old unverified notes inside `2_plausibility.md`.
  They stay unverified. See `2_plausibility.md:419`.

## Unresolved items

- C1 to C7 in section 5. Each needs a unification decision.
  C1 and C2 also need the later BENCHMARK edit stage.
- Exact Rep call count inside 200. Owned by file `13_`.
  This file sets no number. See D8.
- Interval method choice. File `8_` must pick one method.
  This file requires an interval. It does not pick the formula.
- Pilot repeat counts for U6. File `7_` must set them.
  They must fit pilot budget in file `13_`.
- Judge calibration minimum beyond 100 cases.
  File `8_` must set it with sensitivity targets.
  U10 requires correction. It does not fix the set size.
- Refresh cadence after v1. See C3.
  No verified standard sets it for this benchmark type.
- Human baseline need in v1 pilot. See U4 and C4.
  HCAST shows value. Cost and time are unpriced here.
  File `13_` must price it or drop it with a note.
- Whether main tables carry intervals in v1. See C5.
  Literature says yes. BENCHMARK counts-only says wait.
  Unification decides. BENCHMARK edit follows user review.

## Handoff notes for unification

Lift U1 and U8 fields into file `6_` card verbatim.
Keep share-only rule wording. See C1.
Lift U3, U5, U6 and U10 fields into file `8_` verbatim.
Keep S3j deterministic and primary. Judges stay secondary.
Lift U4, U9 and gate wording into file `7_` verbatim.
Keep D4 numbers exact: 30 rows, 10 values, 1 join,
5 steps or sum tool, 40 to 60 design calls, 200 budget,
90 percent and 80 percent gates.
Do not re-derive gate numbers from section 8 prose.
Files `10_` to `13_` add seed policy and scaffold version.
File `13_` alone sets Rep calls inside 200.
File `9_` reuses U6 buckets for Track 0 only if budget allows.
Flag every C item in `14_unified_design.md`. Do not hide them.
This file proposes. Unification decides. BENCHMARK waits.
