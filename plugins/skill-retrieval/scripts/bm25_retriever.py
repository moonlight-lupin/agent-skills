"""BM25 skill retriever — indexes active skill descriptions and ranks them per query.

Adapted from SR-Agents (oneal2000/SR-Agents, MIT license).
Source: https://github.com/oneal2000/SR-Agents/blob/main/src/sragents/retrieve/bm25.py
Indexed once at plugin load; retrieval is sub-millisecond for 128 skills.
"""

import re
import time
import logging
from pathlib import Path

import numpy as np
from scipy import sparse

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

SKILLS_ROOT = Path.home() / ".hermes" / "skills"
PLUGINS_ROOT = Path.home() / ".hermes" / "plugins"
CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"

# Directories under any plugin's skills/ tree to skip (mirrors the
# .archive / .curator_backups / .hub exclusions used for standalone skills).
_SKIP_DIRS = (".archive", ".curator_backups", ".hub")

K1 = 1.5
B = 0.75


# ─── Tokenizer ────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer, lowercased."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


# ─── Skill corpus loader ──────────────────────────────────────────────────────

def _parse_skill_md(skill_md: Path) -> tuple[str, str] | None:
    """Return (name, description) parsed from a SKILL.md frontmatter.

    Returns ("", "") for valid frontmatter with missing name/description.
    Returns ("", "") for invalid frontmatter (no fences, malformed YAML,
    non-mapping). Never raises.
    """
    import yaml

    text = skill_md.read_text(errors="replace")
    lines = text.splitlines()

    # Frontmatter must start at the first line (allowing optional BOM).
    first_line = lines[0].lstrip("\ufeff").strip() if lines else ""
    if first_line != "---":
        logger.warning("No YAML frontmatter in %s (first line is not '---')", skill_md)
        return "", ""

    # Find the closing fence.
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        logger.warning("No closing YAML frontmatter fence in %s", skill_md)
        return "", ""

    fm_text = "\n".join(lines[1:close_idx])
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        logger.warning("Malformed YAML frontmatter in %s", skill_md)
        return "", ""

    if not isinstance(data, dict):
        logger.warning("Non-mapping YAML frontmatter in %s", skill_md)
        return "", ""

    name = data.get("name")
    desc = data.get("description")
    if name is None or desc is None:
        logger.warning("Missing name or description in frontmatter of %s", skill_md)

    name_str = "" if name is None else str(name)
    desc_str = "" if desc is None else str(desc)
    return name_str, desc_str


def _iter_skill_files(root: Path, prefix: str = "") -> list[tuple[Path, str, str]]:
    """Walk `root` for SKILL.md files. Returns [(path, skill_id, leaf_name), ...].

    `prefix` is prepended to the relative id (e.g. "chief-of-staff:") so
    plugin-bundled skills can't collide with standalone ones.
    """
    out: list[tuple[Path, str, str]] = []
    if not root.exists():
        return out
    for skill_md in sorted(root.rglob("SKILL.md")):
        rel_parts = skill_md.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        skill_dir = skill_md.parent
        rel_name = prefix + str(skill_dir.relative_to(root))
        leaf_name = skill_dir.name
        out.append((skill_md, rel_name, leaf_name))
    return out


def load_active_skills() -> list[dict]:
    """Load all non-disabled skills with their descriptions.

    Indexes both standalone skills (~/.hermes/skills) and plugin-bundled
    skills (~/.hermes/plugins/<plugin>/skills). Plugin skills are keyed as
    "<plugin>:<leaf>" so they never collide with standalone ids.
    """
    import yaml

    # Load disabled list
    disabled = set()
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        if not isinstance(config, dict):
            config = {}
        disabled = set(config.get("skills", {}).get("disabled", []))

    # Collect candidate skill files from both roots.
    candidates: list[tuple[Path, str, str]] = []
    candidates += _iter_skill_files(SKILLS_ROOT)
    if PLUGINS_ROOT.exists():
        for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            plugin_skills = plugin_dir / "skills"
            if plugin_skills.is_dir():
                candidates += _iter_skill_files(plugin_skills, prefix=f"{plugin_dir.name}:")

    skills: list[dict] = []
    for skill_md, rel_name, leaf_name in candidates:
        # Disabled list uses bare leaf names and rel_names; match either.
        if leaf_name in disabled or rel_name in disabled:
            continue

        parsed = _parse_skill_md(skill_md)
        if parsed is None:
            continue
        name, desc = parsed
        if not name:
            name = leaf_name

        skills.append({
            "skill_id": rel_name,
            "leaf_name": leaf_name,
            "name": name,
            "description": desc,
            "text": f"{name}: {desc}",
        })

    return skills


# ─── BM25 Index ───────────────────────────────────────────────────────────────

class BM25Index:
    """BM25 Okapi retriever using scipy sparse matrices."""

    def __init__(self, k1: float = K1, b: float = B):
        self.k1 = k1
        self.b = b
        self._built = False

    def build(self, corpus_ids: list[str], corpus_texts: list[str]) -> None:
        self._corpus_ids = corpus_ids
        t0 = time.time()

        # Tokenize and build vocabulary
        vocab: dict[str, int] = {}
        tokenized: list[list[str]] = []
        doc_lens: list[int] = []
        for text in corpus_texts:
            tokens = tokenize(text)
            tokenized.append(tokens)
            doc_lens.append(len(tokens))
            for t in tokens:
                if t not in vocab:
                    vocab[t] = len(vocab)

        avgdl = float(np.mean(doc_lens)) if doc_lens else 1.0
        n_docs = len(corpus_texts)
        n_terms = len(vocab)
        self._vocab = vocab

        # Build TF matrix
        rows, cols, vals = [], [], []
        for i, tokens in enumerate(tokenized):
            if not tokens:
                continue
            counts: dict[int, int] = {}
            for t in tokens:
                tid = vocab[t]
                counts[tid] = counts.get(tid, 0) + 1
            for tid, count in counts.items():
                rows.append(i)
                cols.append(tid)
                vals.append(count)

        tf = sparse.csr_matrix(
            (vals, (rows, cols)), shape=(n_docs, n_terms), dtype=np.float32
        )

        # BM25 saturation
        k1, b = self.k1, self.b
        dl = np.array(doc_lens, dtype=np.float32)
        denom_base = k1 * (1.0 - b + b * dl / avgdl)
        tf_coo = tf.tocoo()
        sat_vals = (tf_coo.data * (k1 + 1)) / (tf_coo.data + denom_base[tf_coo.row])
        bm25_tf = sparse.csr_matrix(
            (sat_vals, (tf_coo.row, tf_coo.col)), shape=(n_docs, n_terms), dtype=np.float32
        )

        # IDF (clipped at zero — Lucene/Elasticsearch variant)
        df = np.array((tf > 0).sum(axis=0), dtype=np.float32).flatten()
        idf = np.log((n_docs - df + 0.5) / (df + 0.5)).clip(min=0)

        self._matrix = bm25_tf.multiply(idf[np.newaxis, :]).tocsr()
        self._built = True
        logger.info("BM25 index built: %d docs, %d terms, %d nnz in %.3fs",
                     n_docs, n_terms, self._matrix.nnz, time.time() - t0)

    def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Return [(skill_id, score), ...] sorted by descending score."""
        if not self._built:
            return []

        tokens = tokenize(query)
        q_rows, q_cols, q_vals = [], [], []
        seen: set[int] = set()
        for t in tokens:
            if t in self._vocab:
                tid = self._vocab[t]
                if tid not in seen:
                    seen.add(tid)
                    q_rows.append(0)
                    q_cols.append(tid)
                    q_vals.append(1.0)

        if not q_vals:
            return []

        q_mat = sparse.csr_matrix(
            (q_vals, (q_rows, q_cols)), shape=(1, len(self._vocab)), dtype=np.float32
        )
        scores = q_mat.dot(self._matrix.T).toarray()[0]
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [
            (self._corpus_ids[idx], float(scores[idx]))
            for idx in top_indices
            if scores[idx] > 0
        ]


# ─── Singleton index ─────────────────────────────────────────────────────────

_index: BM25Index | None = None
_skills_by_id: dict[str, dict] = {}


def get_index() -> BM25Index | None:
    global _index, _skills_by_id
    if _index is not None:
        return _index

    skills = load_active_skills()
    if not skills:
        logger.warning("No active skills found for BM25 index")
        return None

    _index = BM25Index()
    _index.build(
        [s["skill_id"] for s in skills],
        [s["text"] for s in skills],
    )
    _skills_by_id = {s["skill_id"]: s for s in skills}
    return _index


def get_skill_info(skill_id: str) -> dict | None:
    return _skills_by_id.get(skill_id)