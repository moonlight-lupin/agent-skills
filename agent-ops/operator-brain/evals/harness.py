#!/usr/bin/env python3
"""Tool-using agent harness for behavioral-skill A/B batteries.

Runs one OpenRouter chat-completions agent with tools (web_search, web_fetch,
list_dir, read_file, write_file, run_shell). File tools are restricted to the
workspace; run_shell's environment is scrubbed but the shell is NOT sandboxed —
it runs as the harness user and can read host files and the parent process's
environment (e.g. /proc/$PPID/environ). For untrusted subjects, run the
harness in a container. Arms differ ONLY in the injected system text; traces
are written as a single JSON object whose message stream carries per-turn
tool-call counts (the objective batching metric).

Usage: python3 harness.py <system.txt|none> <task.txt> <workspace> <trace.json>
Env: OPENROUTER_API_KEY, HARNESS_MODEL (default thinkingmachines/inkling-small),
HARNESS_MAX_TURNS (default 12). Search pool: Wikipedia + Hacker News
(keyless JSON); disclose to subjects.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error, html.parser, re

MODEL = os.environ.get("HARNESS_MODEL", "thinkingmachines/inkling-small")
API = "https://openrouter.ai/api/v1/chat/completions"
KEY = os.environ["OPENROUTER_API_KEY"]
MAX_TURNS = int(os.environ.get("HARNESS_MAX_TURNS", "12"))

class TextStrip(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.skip += 1
        if tag in ("p","br","li","h1","h2","h3","tr"): self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script","style") and self.skip: self.skip -= 1
    def handle_data(self, d):
        if not self.skip: self.parts.append(d)

def web_search(query):
    """Search the web (Wikipedia + Hacker News pool). Returns title/url/snippet + source label. If zero results, retry with fewer keywords."""
    def wiki(q):
        u = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=" + urllib.parse.quote(q) + "&format=json&srlimit=4"
        out = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "harness"}), timeout=20).read())["query"]["search"]
        return [{"source": "wikipedia", "title": r["title"], "url": "https://en.wikipedia.org/wiki/" + r["title"].replace(" ", "_"),
                 "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", ""))[:250]} for r in out]
    def hn(q):
        u = "https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(q) + "&hitsPerPage=4"
        out = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "harness"}), timeout=20).read())["hits"]
        res = []
        for hit in out:
            if not hit.get("title"): continue
            url = hit.get("url") or ("https://news.ycombinator.com/item?id=" + str(hit["objectID"]))
            res.append({"source": "hackernews", "title": hit["title"], "url": url,
                        "snippet": (hit.get("story_text") or "")[:250], "points": hit.get("points"), "comments": hit.get("num_comments")})
        return res or [{"source": "hackernews", "discussion_only": True, "title": "(no titled story hits; try fewer or different keywords)"}]
    results, tried = [], [query]
    words = query.split()
    if len(words) > 2: tried.append(" ".join(words[:3]))
    if len(words) > 1: tried.append(" ".join(words[:2]))
    used = None
    for q in tried:
        try:
            results = wiki(q)
        except Exception as e:
            results = [{"source": "wikipedia", "error": str(e)}]
        if results and "error" not in results[0]:
            used = q; break
    hnres = []
    try:
        hnres = hn(used or query)
    except Exception as e:
        hnres = [{"source": "hackernews", "error": str(e)}]
    return {"results": (results if results else [{"source": "wikipedia", "note": "no hits even after keyword reduction"}]) + hnres, "queried_as": used or query, "pool": "wikipedia + hackernews only"}

def web_fetch(url):
    if not url.startswith("http"): return {"error": "http(s) only"}
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    ts = TextStrip(); ts.feed(body)
    text = re.sub(r"\n{3,}", "\n\n", "".join(ts.parts)).strip()
    return {"url": url, "chars": len(text), "truncated": len(text) > 4000, "text": text[:4000]}

def jailed(ws, p):
    p = os.path.realpath(os.path.join(ws, p))
    if not p.startswith(os.path.realpath(ws) + os.sep) and p != os.path.realpath(ws):
        return None
    return p

def make_tools(ws):
    def list_dir(path="."):
        p = jailed(ws, path)
        if p is None: return {"error": "outside workspace"}
        return {"entries": sorted(os.listdir(p))}
    def read_file(path):
        p = jailed(ws, path)
        if p is None: return {"error": "outside workspace"}
        if not os.path.isfile(p): return {"error": f"file not found: {path}"}
        return {"path": path, "content": open(p).read()[:8000]}
    def write_file(path, content):
        p = jailed(ws, path)
        if p is None: return {"error": "outside workspace"}
        open(p, "w").write(content)
        return {"ok": True, "path": path, "bytes": len(content)}
    def run_shell(command):
        # env is scrubbed, but this is NOT a sandbox: the child runs as the
        # harness user and can read host files and the parent's original
        # environment via /proc. For untrusted subjects, run in a container.
        r = subprocess.run(["sh", "-c", command], capture_output=True, text=True, timeout=10, cwd=ws,
                           env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C", "HOME": ws})
        return {"exit_code": r.returncode, "stdout": r.stdout[:4000], "stderr": r.stderr[:2000]}
    return {
        "web_search": (web_search, {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        "web_fetch": (web_fetch, {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}),
        "list_dir": (list_dir, {"type": "object", "properties": {"path": {"type": "string"}}}),
        "read_file": (read_file, {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
        "write_file": (write_file, {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}),
        "run_shell": (run_shell, {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}),
    }

def call_api(messages, tools, retries=3):
    payload = {"model": MODEL, "messages": messages, "max_tokens": 900, "tools": tools}
    delay = 8
    for i in range(retries):
        req = urllib.request.Request(API, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if "choices" in r: return r
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            if e.code == 429 and i < retries - 1:
                time.sleep(delay); delay *= 2; continue
            return {"error": f"HTTP {e.code}: {body}"}
        except Exception as e:
            if i < retries - 1: time.sleep(delay); delay *= 2; continue
            return {"error": str(e)}
    return {"error": "retries exhausted"}

def main():
    system_file, task_file, ws, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    os.makedirs(ws, exist_ok=True)
    neutral = "You are a senior operator answering a user request. You have real tools operating in your workspace directory on this machine."
    if system_file != "none":
        neutral += "\n\n" + open(system_file).read()
    task = open(task_file).read()
    tmap = make_tools(ws)
    oapi_tools = [{"type": "function", "function": {"name": n, "description": (d.__doc__ or n).strip(), "parameters": p}} for n, (d, p) in tmap.items()]
    messages = [{"role": "system", "content": neutral}, {"role": "user", "content": task}]
    trace = {"arm": os.path.basename(system_file), "task_text": task, "model": MODEL,
             "system_preview": neutral[:2000], "messages": [], "turns": 0}
    t0 = time.time()
    for turn in range(MAX_TURNS):
        resp = call_api(messages, oapi_tools)
        if "error" in resp:
            trace["messages"].append({"turn": turn, "api_error": resp["error"]}); break
        msg = resp["choices"][0]["message"]
        trace["usage_turns"] = trace.get("usage_turns", []) + [resp.get("usage", {})]
        tcalls = msg.get("tool_calls") or []
        trace["messages"].append({"turn": turn, "role": "assistant", "content": msg.get("content"), "n_tool_calls": len(tcalls), "tool_names": [t["function"]["name"] for t in tcalls]})
        trace["turns"] = turn + 1
        if not tcalls:
            break
        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tcalls})
        for t in tcalls:
            fn, args = t["function"]["name"], t["function"].get("arguments") or "{}"
            try:
                args = json.loads(args) if isinstance(args, str) else args
                result = tmap[fn][0](**args)
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            trace["messages"].append({"turn": turn, "role": "tool", "name": fn, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": t.get("id"), "name": fn, "content": json.dumps(result)[:6000]})
    trace["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(trace, open(out, "w"), indent=1)  # JSON (single object), not JSONL
    # final text to stdout for convenience
    for m in reversed(trace["messages"]):
        if m.get("role") == "assistant" and m.get("content"):
            print(m["content"]); break

if __name__ == "__main__":
    main()
