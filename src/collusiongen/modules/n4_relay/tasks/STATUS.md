# N4 task inventory: status

Finished model games out of planned (every setting × 2, 3, 4 agents × unprompted
and told × the model's runs). Written by `scripts/experiments.py status --write`
from the local copies of the runs.

| Task | Setup | DeepSeek V4.1 Flash | GLM-5.3-Flash | K2-Horizon-0.9B | K2-Horizon-3.7B | K2-Horizon-32B FP8 | K2-Horizon-7B | K2-Horizon-MoVA FP8 |
|---|---|---|---|---|---|---|---|---|
| survey_v1 | Four channels | 0/24 | 24/120 | 120/120 | 120/120 | 120/120 | 120/120 | 120/120 |
| survey_v1 | Message cap | 0/60 | 60/300 | 300/300 | 300/300 | 300/300 | 300/300 | 300/300 |
| depot_v1 | Four channels | 0/24 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 |
| depot_v1 | Message cap | 0/60 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 |
| depot_v2 | Four channels | 0/24 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 |
| depot_v2 | Message cap | 0/60 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 |
| seating_v1 | Four channels | 0/24 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 |
| seating_v1 | Message cap | 0/60 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 |
| word_v1 | Four channels | 0/24 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 | 0/120 |
| word_v1 | Message cap | 0/60 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 | 0/300 |
