import json, sys
n=json.load(open(f'/private/tmp/claude-501/-Users-chenghengli-Desktop-semester-project/cf8e5b8d-1387-44e3-b034-6824de9e85b8/scratchpad/{sys.argv[1]}_notes.json'))
for t,parts in n['tasks'].items():
    print('\n########', t)
    for p in parts:
        print('--', p['part']); print('SOLVED:', p['how_solved']); print('FAILED:', p['why_failed']); print('RULE:', p['rule_reasoning'])
        for pt in p['patterns']:
            print(f"  * {pt['name']} ({pt.get('games')}): {pt['what']}")
            for q in pt['quotes']: print(f"      [{q['kind']}] \"{q['text']}\" ({q['game'][:6]} a{q['agent']})")
        for o in p['odd']: print(f"  ODD \"{o['text']}\" ({o['game'][:6]}) — {o['why']}")
