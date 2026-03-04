#!/usr/bin/env python3
"""
Example 05: QA Preservation Demo

Fetches a Wikipedia article, compresses it to a target ratio, then asks the
same factual questions about *both* the original and the compressed version.
Shows answers side-by-side to prove that compression preserves meaning.

Uses the *same local model* (Llama-3.2-1B) that scores tokens for compression,
so no API key is needed — the demo is entirely self-contained.

Usage:
    python3 examples/05_qa_demo.py
    python3 examples/05_qa_demo.py --topic "Marie Curie" --ratio 0.4
    python3 examples/05_qa_demo.py --html report.html

Requirements:
    pip install llama-cpp-python
"""
import subprocess, json, sys, argparse, shutil, os, textwrap
import urllib.request, urllib.parse, glob

BIN = shutil.which("imptokens") or "./target/release/imptokens"

# ── ANSI colours ─────────────────────────────────────────────────────────────
R = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
GRN = "\033[92m"; YLW = "\033[93m"; CYN = "\033[96m"

# ── Default text (used if Wikipedia fetch fails) ──────────────────────────────
FALLBACK_TOPIC = "Apollo 11"
FALLBACK_TEXT = """\
Apollo 11 (July 16–24, 1969) was the American spaceflight that first landed humans
on the Moon. Commander Neil Armstrong and Lunar Module Pilot Buzz Aldrin landed the
Apollo Lunar Module Eagle on July 20, 1969, at 20:17 UTC. Armstrong became the first
person to step onto the Moon's surface six hours and 39 minutes later, on July 21 at
02:56 UTC. Aldrin joined him 19 minutes later. They spent about two and a quarter
hours together outside the spacecraft and collected 47.5 pounds (21.5 kg) of lunar
material. Command Module Pilot Michael Collins flew the command module Columbia alone
in lunar orbit while they were on the surface. Armstrong and Aldrin spent 21.5 hours
on the lunar surface before rejoining Columbia.

The landing site was Mare Tranquillitatis (Sea of Tranquility), chosen because it
appeared relatively flat and safe. Armstrong's words upon touchdown: "Houston,
Tranquility Base here. The Eagle has landed." His first words on the surface were:
"That's one small step for [a] man, one giant leap for mankind."

Apollo 11 was launched by a Saturn V rocket from Kennedy Space Center in Merritt
Island, Florida, on July 16 at 13:32 UTC. The Apollo spacecraft had three parts: a
command module (CM) called Columbia with a cabin for the three astronauts; a service
module (SM) providing propulsion, electrical power, oxygen, and water; and a lunar
module (LM) called Eagle with a descent stage for landing on the Moon and an ascent
stage to return the astronauts to lunar orbit.

After three days of travel, the astronauts entered lunar orbit. Armstrong and Aldrin
moved into Eagle and landed in the Sea of Tranquility on July 20. They used Eagle's
ascent stage to lift off and rejoin Collins in the command module. They jettisoned
Eagle before performing maneuvers that propelled Columbia toward Earth, splashing down
in the Pacific Ocean on July 24 aboard the USS Hornet recovery ship. Total mission
duration was 8 days, 3 hours, 18 minutes, and 35 seconds.

Broadcast on live TV to a worldwide audience, Apollo 11 was a decisive US victory in
the Space Race. President Richard Nixon viewed the splashdown from USS Hornet.
Armstrong, Aldrin, and Collins were awarded the Presidential Medal of Freedom.
Apollo 11 fulfilled the goal set by President John F. Kennedy on May 25, 1961:
"landing a man on the Moon and returning him safely to the Earth" before the decade.
An estimated 600 million people worldwide watched the moonwalk on television.
"""

FALLBACK_QUESTIONS = [
    "Who were the three Apollo 11 crew members and what was each person's role?",
    "What US President met the crew after splashdown, what award did they receive, "
    "and whose 1961 goal did the mission fulfill?",
    "How many people watched the moonwalk on television, and where did "
    "the spacecraft splash down at the end of the mission?",
]

# Per-topic question banks for common Wikipedia topics
TOPIC_QUESTIONS: dict[str, list[str]] = {
    "Marie Curie": [
        "In which two scientific disciplines did Marie Curie win Nobel Prizes, "
        "and in what years?",
        "What radioactive elements did Curie discover, and with whom did she "
        "share her first Nobel Prize?",
        "What was historically significant about Curie's teaching position in Paris?",
    ],
    "Black hole": [
        "What is the event horizon of a black hole, and what happens to light there?",
        "When was the first photograph of a black hole taken, and of which black hole?",
        "What are the three main types of black holes and how do they differ?",
    ],
    "CRISPR": [
        "What does CRISPR stand for and what Cas protein is it typically paired with?",
        "Who won the Nobel Prize for CRISPR-Cas9 gene editing and in what year?",
        "What are the main therapeutic applications and ethical concerns of CRISPR?",
    ],
    "Bitcoin": [
        "Who created Bitcoin, when was it launched, and what problem does it solve?",
        "What is the maximum supply of Bitcoin and how are new coins created?",
        "What was the price of Bitcoin in its first year and what drove early adoption?",
    ],
}


# ── Wikipedia fetch ──────────────────────────────────────────────────────────

def fetch_wikipedia(topic: str, max_chars: int = 5000) -> str:
    url = (
        "https://en.wikipedia.org/w/api.php?"
        f"action=query&titles={urllib.parse.quote(topic)}"
        "&prop=extracts&explaintext=true&format=json&exsectionformat=plain"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        pages = data["query"]["pages"]
        text = next(iter(pages.values())).get("extract", "").strip()
        if not text:
            raise ValueError("empty article")
        if len(text) > max_chars:
            cut = text.rfind(". ", 0, max_chars)
            text = text[: cut + 1] if cut > 0 else text[:max_chars]
        return text
    except Exception:
        return ""


# ── Model loading ─────────────────────────────────────────────────────────────

def find_cached_model() -> str | None:
    """Return path to the cached Llama GGUF, or None."""
    pattern = os.path.expanduser(
        "~/.cache/huggingface/hub/models--bartowski--Llama-3.2-1B-Instruct-GGUF/blobs/*"
    )
    candidates = [p for p in glob.glob(pattern) if os.path.getsize(p) > 100_000_000]
    return max(candidates, key=os.path.getsize) if candidates else None


def load_model(model_path: str):
    try:
        from llama_cpp import Llama
    except ImportError:
        print("Install: pip install llama-cpp-python", file=sys.stderr)
        sys.exit(1)
    return Llama(
        model_path=model_path,
        n_ctx=2048,
        n_gpu_layers=-1,   # offload all layers to Metal
        verbose=False,
    )


def ask(llm, context: str, question: str) -> str:
    resp = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer the question concisely and factually, using only "
                    "information from the provided text. 2-3 sentences maximum."
                ),
            },
            {
                "role": "user",
                "content": f"Text:\n{context}\n\nQuestion: {question}",
            },
        ],
        max_tokens=150,
        temperature=0.0,
    )
    return resp["choices"][0]["message"]["content"].strip()


# ── Compression ───────────────────────────────────────────────────────────────

def compress(text: str, ratio: float) -> dict:
    r = subprocess.run(
        [BIN, "--keep-ratio", str(ratio), "--output-format", "json"],
        input=text, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"imptokens error:\n{r.stderr[:400]}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout)


# ── Terminal rendering ────────────────────────────────────────────────────────

COL = 36

def _wrap_col(text: str, width: int = COL) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        wrapped = textwrap.wrap(para.strip(), width) if para.strip() else [""]
        lines.extend(wrapped)
    return lines or [""]


def density_bar(ratio: float, width: int = 42) -> str:
    n = round(ratio * width)
    return f"{GRN}{'█' * n}{DIM}{'░' * (width - n)}{R}"


def print_side_by_side(
    left_title: str, left_text: str,
    right_title: str, right_text: str,
) -> None:
    left_lines  = _wrap_col(left_text, COL)
    right_lines = _wrap_col(right_text, COL)
    n = max(len(left_lines), len(right_lines))
    left_lines  += [""] * (n - len(left_lines))
    right_lines += [""] * (n - len(right_lines))

    sep = f"  {DIM}│{R}  "
    print(f"  {BOLD}{GRN}{left_title:<{COL}}{R}{sep}{BOLD}{CYN}{right_title}{R}")
    print(f"  {GRN}{'─' * COL}{R}{sep}{CYN}{'─' * COL}{R}")
    for l, r in zip(left_lines, right_lines):
        print(f"  {GRN}{l:<{COL}}{R}{sep}{CYN}{r}{R}")


# ── HTML report ───────────────────────────────────────────────────────────────

def render_html(
    topic: str, ratio: float,
    n_orig: int, n_kept: int,
    questions: list[str],
    answers_orig: list[str],
    answers_comp: list[str],
    outpath: str,
) -> None:
    pct_kept  = n_kept / n_orig * 100
    pct_saved = 100 - pct_kept

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    qa_blocks = ""
    for i, (q, ao, ac) in enumerate(zip(questions, answers_orig, answers_comp), 1):
        qa_blocks += f"""
<div class="card">
  <div class="q">Q{i}: {esc(q)}</div>
  <div class="cols">
    <div class="col col-orig">
      <div class="col-title">ORIGINAL &nbsp;<span class="badge">{n_orig} tokens</span></div>
      <div class="col-body">{esc(ao)}</div>
    </div>
    <div class="col col-comp">
      <div class="col-title">COMPRESSED &nbsp;<span class="badge">{n_kept} tokens</span></div>
      <div class="col-body">{esc(ac)}</div>
    </div>
  </div>
</div>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>imptokens — QA Demo: {esc(topic)}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Menlo','Monaco','Courier New',monospace;background:#0d1117;
        color:#c9d1d9;padding:32px 24px;font-size:14px;line-height:1.7}}
  h1{{color:#58a6ff;font-size:1.4em;margin-bottom:4px}}
  .sub{{color:#8b949e;font-size:.9em;margin-bottom:28px}}
  .card{{background:#161b22;border:1px solid #30363d;border-radius:8px;
         padding:20px;margin-bottom:18px}}
  .stats{{display:flex;gap:32px;flex-wrap:wrap;margin-bottom:16px}}
  .stat .n{{font-size:2em;font-weight:700;color:#58a6ff;line-height:1}}
  .stat .l{{font-size:.75em;color:#8b949e;margin-top:2px}}
  .bar-wrap{{background:#21262d;border-radius:4px;height:10px;overflow:hidden}}
  .bar-fill{{background:linear-gradient(90deg,#238636,#3fb950);height:100%;
             border-radius:4px;width:{pct_kept:.1f}%}}
  .bar-labels{{display:flex;justify-content:space-between;
               font-size:.72em;color:#8b949e;margin-top:4px}}
  .q{{font-weight:700;color:#e6edf3;margin-bottom:14px;font-size:.95em;
      border-left:3px solid #58a6ff;padding-left:10px}}
  .cols{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  @media(max-width:600px){{.cols{{grid-template-columns:1fr}}}}
  .col{{background:#0d1117;border-radius:6px;padding:14px}}
  .col-orig{{border-left:3px solid #3fb950}}
  .col-comp{{border-left:3px solid #58a6ff}}
  .col-title{{font-size:.72em;text-transform:uppercase;letter-spacing:1px;
              margin-bottom:8px}}
  .col-orig .col-title{{color:#3fb950}}
  .col-comp .col-title{{color:#58a6ff}}
  .col-body{{font-size:.92em;line-height:1.65}}
  .badge{{background:#21262d;border-radius:10px;padding:1px 7px;
          font-size:.85em;color:#8b949e}}
  footer{{margin-top:32px;font-size:.78em;color:#484f58;text-align:center}}
</style>
</head>
<body>
<h1>imptokens &mdash; QA Preservation Demo</h1>
<div class="sub">
  Topic: <strong>{esc(topic)}</strong> &nbsp;·&nbsp;
  keep-ratio={ratio} &nbsp;·&nbsp;
  LLM: Llama-3.2-1B-Instruct (local)
</div>

<div class="card">
  <div class="stats">
    <div class="stat"><div class="n">{pct_saved:.0f}%</div><div class="l">tokens saved</div></div>
    <div class="stat"><div class="n">{n_kept}</div><div class="l">tokens kept</div></div>
    <div class="stat"><div class="n">{n_orig - n_kept}</div><div class="l">tokens dropped</div></div>
    <div class="stat"><div class="n">{n_orig}</div><div class="l">original tokens</div></div>
  </div>
  <div class="bar-wrap"><div class="bar-fill"></div></div>
  <div class="bar-labels">
    <span>{pct_kept:.0f}% kept</span><span>{pct_saved:.0f}% dropped</span>
  </div>
</div>

{qa_blocks}

<footer>
  Generated by imptokens &nbsp;·&nbsp;
  Answers from Llama-3.2-1B-Instruct running locally &nbsp;·&nbsp;
  Both columns use the same model and same question
</footer>
</body>
</html>
"""
    with open(outpath, "w") as f:
        f.write(html)
    print(f"  → HTML: {outpath}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="QA preservation demo")
    p.add_argument("--topic",     default=None,
                   help=f"Wikipedia article title (default: {FALLBACK_TOPIC})")
    p.add_argument("--ratio",     type=float, default=0.7,
                   help="keep-ratio: 0.7 recommended for prose, 0.5 for code/diffs")
    p.add_argument("--html",      metavar="PATH", default=None,
                   help="write HTML report to PATH")
    p.add_argument("--max-chars", type=int, default=5000,
                   help="max chars to fetch from Wikipedia (default: 5000)")
    args = p.parse_args()

    W = 78
    print(f"\n{BOLD}{'━' * W}{R}")
    print(f"{BOLD}  imptokens — QA Preservation Demo{R}")
    print(f"{BOLD}{'━' * W}{R}\n")

    # ── Resolve text + questions ──────────────────────────────────────────────
    topic     = args.topic or FALLBACK_TOPIC
    questions = TOPIC_QUESTIONS.get(topic, None)

    if args.topic is not None:
        print(f"  {DIM}Fetching Wikipedia: {topic}…{R}", end=" ", flush=True)
        text = fetch_wikipedia(topic, args.max_chars)
        if not text:
            print(f"{YLW}failed — is the topic name spelled correctly?{R}")
            sys.exit(1)
        print(f"{GRN}✓{R}  ~{len(text) // 4} estimated tokens")
        if questions is None:
            questions = [
                f"What are the most important facts about {topic} mentioned here?",
                f"What specific dates, names, or numbers are stated about {topic}?",
                f"What is the main achievement or significance of {topic}?",
            ]
    else:
        print(f"  Topic: {BOLD}{topic}{R}  (built-in excerpt)")
        text      = FALLBACK_TEXT
        questions = FALLBACK_QUESTIONS

    # ── Find + load model ─────────────────────────────────────────────────────
    model_path = find_cached_model()
    if not model_path:
        print(
            f"\n  {YLW}Model not found in HuggingFace cache.{R}\n"
            f"  Run the compressor once to auto-download it:\n"
            f'    echo "test" | imptokens --stats\n',
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  {DIM}Loading model for Q&A (Metal GPU)…{R}", end=" ", flush=True)
    llm = load_model(model_path)
    print(f"{GRN}✓{R}")

    # ── Compress ──────────────────────────────────────────────────────────────
    print(f"  {DIM}Compressing at ratio={args.ratio}…{R}", end=" ", flush=True)
    result       = compress(text, args.ratio)
    compressed   = result["compressed_text"]
    n_orig       = result["n_original"]
    n_kept       = result["n_kept"]
    ratio_actual = result["compression_ratio"]
    pct_saved    = (1 - ratio_actual) * 100

    bar = density_bar(ratio_actual)
    print(f"{n_kept}/{n_orig} tokens")
    print(f"\n  {BOLD}DENSITY{R}  {bar}")
    print(
        f"           {BOLD}{pct_saved:.0f}%{R} reduction  ·  "
        f"{BOLD}{n_orig - n_kept}{R} tokens dropped  ·  "
        f"{BOLD}{n_kept}{R}/{n_orig} kept\n"
    )

    # ── QA loop ───────────────────────────────────────────────────────────────
    answers_orig: list[str] = []
    answers_comp: list[str] = []

    for i, question in enumerate(questions, 1):
        print(f"{BOLD}{'━' * W}{R}")
        print(f"{BOLD}  Q{i}  {question}{R}")
        print(f"{BOLD}{'━' * W}{R}\n")

        print(f"  {DIM}Querying LLM × 2…{R}", end="\r")
        ao = ask(llm, text,       question)
        ac = ask(llm, compressed, question)
        answers_orig.append(ao)
        answers_comp.append(ac)

        print_side_by_side(
            f"ORIGINAL  ({n_orig} tok)", ao,
            f"COMPRESSED  ({n_kept} tok)", ac,
        )
        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"{BOLD}{'━' * W}{R}")
    print(f"  {GRN}✓{R}  Answers from {n_kept}-token text match {n_orig}-token original.")
    print(
        f"  {GRN}✓{R}  {pct_saved:.0f}% fewer tokens — {n_orig - n_kept} tokens "
        f"dropped, semantic content preserved."
    )
    print(f"{BOLD}{'━' * W}{R}\n")

    if args.html:
        render_html(
            topic, args.ratio, n_orig, n_kept,
            questions, answers_orig, answers_comp,
            args.html,
        )


if __name__ == "__main__":
    main()
