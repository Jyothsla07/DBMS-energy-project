"""
ask_web.py
A one-page website for asking the energy database questions in plain English.
Uses only Python's built-in web server, so there is nothing extra to install.

python python/ask_web.py
Then open http://localhost:8000 in a browser. Press Ctrl+C to stop.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import nl2sql  # noqa: E402

PORT = int(os.getenv("PORT", "8000"))
ROWS_TO_BROWSER = 500

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask the Energy Database</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem;
         color: #1f2328; background: #fff; }
  h1 { margin-bottom: .2rem; }
  .sub { color: #656d76; margin-top: 0; }
  form { display: flex; gap: .5rem; margin: 1.5rem 0 .5rem; }
  input { flex: 1; padding: .6rem .8rem; font-size: 1rem; border: 1px solid #d0d7de; border-radius: 6px; }
  button { padding: .6rem 1.1rem; font-size: 1rem; border: 0; border-radius: 6px;
           background: #1f6feb; color: #fff; cursor: pointer; }
  button:disabled { background: #8c959f; cursor: wait; }
  .examples a { display: inline-block; margin: .2rem .4rem .2rem 0; color: #1f6feb;
                font-size: .9rem; cursor: pointer; }
  .qa { border-top: 1px solid #d0d7de; padding: 1rem 0; }
  .q { font-weight: 600; }
  .a { margin: .5rem 0; line-height: 1.5; }
  .err { color: #cf222e; }
  details { margin-top: .5rem; }
  summary { cursor: pointer; color: #656d76; }
  pre { background: #f6f8fa; padding: .8rem; border-radius: 6px; overflow-x: auto; }
  .note { color: #656d76; font-size: .85rem; }
  .table-wrap { max-height: 400px; overflow: auto; }
  table { border-collapse: collapse; font-size: .85rem; }
  th, td { border: 1px solid #d0d7de; padding: .3rem .6rem; text-align: right; white-space: nowrap; }
  th { background: #f6f8fa; position: sticky; top: 0; }
</style>
</head>
<body>
<h1>Ask the Energy Database</h1>
<p class="sub">California electricity demand, solar, wind and weather, 2019&ndash;2021, every 5 minutes.
Type a question; a local open-source model writes the SQL and MySQL answers it.</p>

<form id="f">
  <input id="q" autocomplete="off" autofocus
         placeholder="e.g. What was the average solar production at noon in June 2020?">
  <button id="b">Ask</button>
</form>
<div class="examples">Try:
  <a>What was the peak demand each year and when?</a>
  <a>Monthly renewable share in 2021</a>
  <a>Average demand and net load by hour of day</a>
  <a>Top 10 days for solar production</a>
  <a>Weekday vs weekend demand in summer</a>
</div>
<div id="out"></div>

<script>
const history = [];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function table(cols, rows) {
  const head = cols.map(c => `<th>${esc(c)}</th>`).join("");
  const body = rows.map(r => "<tr>" + r.map(v => `<td>${esc(v)}</td>`).join("") + "</tr>").join("");
  return `<div class="table-wrap"><table><tr>${head}</tr>${body}</table></div>`;
}

async function ask(question) {
  const btn = document.getElementById("b");
  btn.disabled = true; btn.textContent = "Working…";
  const box = document.createElement("div");
  box.className = "qa";
  box.innerHTML = `<div class="q">${esc(question)}</div><div class="a note">Writing SQL and querying…</div>`;
  document.getElementById("out").prepend(box);
  try {
    const res = await fetch("/ask", {method: "POST", headers: {"Content-Type": "application/json"},
                                     body: JSON.stringify({question, history})});
    const r = await res.json();
    let html = `<div class="q">${esc(question)}</div>`;
    if (r.error) html += `<div class="a err">${esc(r.error)}</div>`;
    if (r.answer) html += `<div class="a">${esc(r.answer)}</div>`;
    html += `<div class="note">${r.seconds.toFixed(1)} s${r.attempts > 1 ? `, query fixed after ${r.attempts - 1} error(s)` : ""}</div>`;
    if (r.sql) {
      html += `<details${r.error ? " open" : ""}><summary>SQL and data</summary>`;
      html += `<pre>${esc(r.sql)}</pre>`;
      if (r.columns.length) {
        html += `<p class="note">${r.total_rows} rows${r.rows.length < r.total_rows ? `, first ${r.rows.length} shown` : ""}</p>`;
        html += table(r.columns, r.rows);
      }
      html += "</details>";
      if (!r.error) history.push([question, r.sql]);
    }
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = `<div class="q">${esc(question)}</div><div class="a err">Request failed: ${esc(e)}</div>`;
  }
  btn.disabled = false; btn.textContent = "Ask";
}

document.getElementById("f").addEventListener("submit", e => {
  e.preventDefault();
  const q = document.getElementById("q");
  if (q.value.trim()) { ask(q.value.trim()); q.value = ""; }
});
document.querySelectorAll(".examples a").forEach(a => a.addEventListener("click", () => ask(a.textContent)));
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "Not found", "text/plain")

    def do_POST(self):
        if self.path != "/ask":
            return self._send(404, "Not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        question = str(body.get("question", "")).strip()
        history = [tuple(pair) for pair in body.get("history", [])]

        r = nl2sql.ask(question, history)
        shown = r.data.head(ROWS_TO_BROWSER)
        shown = shown.astype(object).where(shown.notna(), None)   # NaN -> null
        table = shown.to_dict(orient="split", index=False)
        reply = {
            "answer": r.answer,
            "sql": r.sql,
            "seconds": r.seconds,
            "attempts": r.attempts,
            "error": r.error,
            "columns": table["columns"],
            "rows": table["data"],
            "total_rows": len(r.data),
        }
        # default=str turns dates and times into readable text (2020-08-18)
        self._send(200, json.dumps(reply, default=str), "application/json")

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


if __name__ == "__main__":
    nl2sql.load_model()   # load once at startup so the first question is not slow
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Open http://localhost:{PORT} in your browser (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
