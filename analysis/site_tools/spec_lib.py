"""Helpers for writing a model page's text: every quote is checked word for word against that
model's digests before it can go on the page."""
import html
import json

SP = "/private/tmp/claude-501/-Users-chenghengli-Desktop-semester-project/cf8e5b8d-1387-44e3-b034-6824de9e85b8/scratchpad"


class Quotes:
    def __init__(self, key):
        self.text = {t: open(f"{SP}/{key}_digest/{t}.txt").read() for t in ("survey_v1", "depot_v1", "seating_v1")}
        self.used = 0

    def __call__(self, text, task=None, plain=False):
        """<i>"text"</i>, after checking the text appears in the task's digest (or any task's)."""
        pool = [self.text[task]] if task else list(self.text.values())
        assert any(text in p for p in pool), f"quote not found: {text[:80]}"
        self.used += 1
        return text if plain else f'<i>"{html.escape(text, quote=False)}"</i>'


def card(title, *paras, muted=None):
    body = "".join(f"<p>{p}</p>" for p in paras)
    if muted:
        body += f'<p class="muted">{muted}</p>'
    return f'      <div class="card"><h3>{title}</h3>\n        {body}</div>'


def peers():
    return json.load(open(f"{SP}/peers.json"))
