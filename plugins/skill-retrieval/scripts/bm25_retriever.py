"""BM25 skill retriever — indexes active skill descriptions and ranks them per query.

Adapted from SR-Agents (oneal2000/SR-Agents, MIT license).
Source: https://github.com/oneal2000/SR-Agents/blob/main/src/sragents/retrieve/bm25.py
Indexed once at plugin load; retrieval is sub-millisecond for 128 skills.
"""

import re
import os
import time
import math
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

try:
    from hermes_constants import get_config_path, get_hermes_home, get_skills_dir
except ImportError:  # pragma: no cover - standalone test fallback
    def get_hermes_home() -> Path:
        val = os.environ.get("HERMES_HOME", "").strip()
        return Path(val).expanduser() if val else Path.home() / ".hermes"

    def get_config_path() -> Path:
        return get_hermes_home() / "config.yaml"

    def get_skills_dir() -> Path:
        return get_hermes_home() / "skills"


def get_plugins_dir() -> Path:
    """Return the profile-scoped plugins directory."""
    return get_hermes_home() / "plugins"


# Backward-compatible test override points. Runtime code resolves paths through
# Hermes' official home helpers on every load so multiplexed/named profiles do
# not read the default profile by accident.
SKILLS_ROOT = get_skills_dir()
PLUGINS_ROOT = get_plugins_dir()
CONFIG_PATH = get_config_path()

# Directories under any plugin's skills/ tree to skip (mirrors the
# .archive / .curator_backups / .hub exclusions used for standalone skills).
_SKIP_DIRS = (".archive", ".curator_backups", ".hub")

K1 = 1.5
B = 0.75


# ─── Tokenizer ────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer, lowercased.

    Defends against non-str queries: Telegram can deliver the user message
    as a list of content parts (str or {"text": ...} dicts). Flatten to a
    plain string before tokenizing; anything else is stringified.
    """
    if not isinstance(text, str):
        if isinstance(text, (list, tuple)):
            parts: list[str] = []
            for part in text:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    value = part.get("text") or part.get("caption")
                    if isinstance(value, str):
                        parts.append(value)
            text = " ".join(parts)
        else:
            text = str(text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


# ─── Skill corpus loader ──────────────────────────────────────────────────────

def _parse_skill_md(skill_md: Path) -> tuple[str, str]:
    """Return (name, description) parsed from a SKILL.md frontmatter.

    Returns ("", "") for valid frontmatter with missing name/description.
    Returns ("", "") for invalid frontmatter (no fences, malformed YAML,
    non-mapping) and for a file that cannot be read. Never raises, so one
    unreadable skill cannot abort the whole index build.
    """
    import yaml

    try:
        text = skill_md.read_text(errors="replace")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", skill_md, exc)
        return "", ""
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


def _runtime_paths_are_overridden() -> bool:
    """Return True when tests monkeypatch the legacy path constants."""
    return (
        SKILLS_ROOT != get_skills_dir()
        or PLUGINS_ROOT != get_plugins_dir()
        or CONFIG_PATH != get_config_path()
    )


def _skill_id_from_entry(entry: dict, prefix: str = "") -> str:
    category = str(entry.get("category") or "general")
    skill_name = str(entry.get("skill_name") or entry.get("frontmatter_name") or "")
    if category and category != "general":
        return f"{prefix}{category}/{skill_name}"
    return f"{prefix}{skill_name}"


def _record_skill(skills: list[dict], seen_names: set[str], entry: dict, *, prefix: str = "") -> None:
    """Append a parsed Hermes skill entry while preserving first-seen precedence."""
    name = str(entry.get("frontmatter_name") or entry.get("skill_name") or "").strip()
    if not name or name in seen_names:
        return
    seen_names.add(name)
    desc = str(entry.get("description") or "")
    skills.append({
        "skill_id": _skill_id_from_entry(entry, prefix=prefix),
        "leaf_name": str(entry.get("skill_name") or name),
        "name": name,
        "description": desc,
        "text": f"{name}: {desc}",
    })


def _load_active_skills_legacy() -> list[dict]:
    """Original standalone loader used by tests that monkeypatch path constants."""
    import yaml

    # Load disabled list and profile-configured external skill directories.
    disabled = set()
    if CONFIG_PATH.exists():
        # A malformed or unreadable config must not abort the index build —
        # that would leave the agent with a compacted prompt and no retrieval.
        try:
            config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning(
                "Cannot read %s: %s — treating no skills as disabled",
                CONFIG_PATH, exc,
            )
            config = {}
        if not isinstance(config, dict):
            config = {}
        skills_cfg = config.get("skills")
        if isinstance(skills_cfg, dict):
            disabled = set(skills_cfg.get("disabled") or [])

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

        name, desc = _parse_skill_md(skill_md)
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


def load_active_skills() -> list[dict]:
    """Load active skills using Hermes' own profile-aware discovery helpers.

    Runtime path/config resolution is delegated to Hermes core helpers so named
    profiles, context-local home overrides, ``skills.external_dirs``, trusted
    project-local skills, disabled lists, platform gates, and condition gates
    match the agent's normal skill index as closely as a plugin can. Plugin-
    bundled skills are scanned from the active profile's plugin directory.
    """
    if _runtime_paths_are_overridden():
        return _load_active_skills_legacy()

    try:
        from agent.prompt_builder import (
            _build_snapshot_entry,
            _current_session_platform_hint,
            _parse_skill_file,
            _skill_should_show,
            extract_skill_conditions,
        )
        from agent.skill_utils import (
            get_all_skills_dirs,
            get_disabled_skill_names,
            get_project_skills_dirs,
            iter_project_skill_files,
            iter_skill_index_files,
        )
    except ImportError as exc:
        logger.warning("Cannot import Hermes skill discovery helpers: %s", exc)
        return _load_active_skills_legacy()

    platform_hint = _current_session_platform_hint() or None
    disabled = get_disabled_skill_names(platform_hint)
    skills: list[dict] = []
    seen_names: set[str] = set()

    def add_skill_file(skill_file: Path, root: Path, *, prefix: str = "") -> None:
        try:
            is_compatible, frontmatter, desc = _parse_skill_file(skill_file)
            if not is_compatible:
                return
            entry = _build_snapshot_entry(skill_file, root, frontmatter, desc)
            if entry["frontmatter_name"] in disabled or entry["skill_name"] in disabled:
                return
            if not _skill_should_show(
                extract_skill_conditions(frontmatter),
                None,
                None,
                platform_hint,
            ):
                return
            _record_skill(skills, seen_names, entry, prefix=prefix)
        except Exception as exc:
            logger.debug("Error reading skill %s: %s", skill_file, exc)

    # Precedence mirrors Hermes: trusted project-local → profile-local →
    # configured external dirs. First seen name wins.
    for project_dir in get_project_skills_dirs():
        for skill_file in iter_project_skill_files(project_dir):
            add_skill_file(skill_file, project_dir)

    all_skill_dirs = get_all_skills_dirs()
    for skill_root in all_skill_dirs:
        for skill_file in iter_skill_index_files(skill_root, "SKILL.md"):
            add_skill_file(skill_file, skill_root)

    plugins_root = get_plugins_dir()
    if plugins_root.exists():
        for plugin_dir in sorted(plugins_root.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            plugin_skills = plugin_dir / "skills"
            if not plugin_skills.is_dir():
                continue
            for skill_file in iter_skill_index_files(plugin_skills, "SKILL.md"):
                add_skill_file(skill_file, plugin_skills, prefix=f"{plugin_dir.name}:")

    return skills


# ─── BM25 Index ───────────────────────────────────────────────────────────────

class BM25Index:
    """BM25 Okapi retriever using a pure-stdlib inverted index.

    At build time, the full BM25 weight for every (term, document) pair is
    precomputed and stored in an inverted index: ``dict[str, list[tuple[int, float]]]``
    mapping each term to a posting list of (doc_index, weight). A query then
    sums weights over the posting lists of the query terms only — no scan over
    the full corpus.
    """

    def __init__(self, k1: float = K1, b: float = B):
        self.k1 = k1
        self.b = b
        self._built = False

    def build(self, corpus_ids: list[str], corpus_texts: list[str]) -> None:
        self._corpus_ids = corpus_ids
        t0 = time.time()

        # Tokenize, build vocabulary, record document lengths.
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

        n_docs = len(corpus_texts)
        avgdl = sum(doc_lens) / n_docs if n_docs else 1.0
        n_terms = len(vocab)
        self._vocab = vocab

        # Document frequency per term.
        df: dict[int, int] = {}
        for tokens in tokenized:
            for tid in set(vocab[t] for t in tokens):
                df[tid] = df.get(tid, 0) + 1

        # Lucene-style clipped IDF: max(0, log((N - df + 0.5) / (df + 0.5))).
        idf: dict[int, float] = {}
        for tid, df_count in df.items():
            val = math.log((n_docs - df_count + 0.5) / (df_count + 0.5))
            idf[tid] = max(0.0, val)

        # Build inverted index with precomputed BM25 weights.
        # term → list of (doc_index, weight)
        k1, b = self.k1, self.b
        nnz = 0
        postings: dict[int, list[tuple[int, float]]] = {}
        for i, tokens in enumerate(tokenized):
            if not tokens:
                continue
            counts: dict[int, int] = {}
            for t in tokens:
                tid = vocab[t]
                counts[tid] = counts.get(tid, 0) + 1
            dl = doc_lens[i]
            denom = k1 * (1.0 - b + b * dl / avgdl)
            for tid, tf in counts.items():
                # BM25 Okapi TF saturation.
                sat = (tf * (k1 + 1.0)) / (tf + denom)
                weight = sat * idf[tid]
                postings.setdefault(tid, []).append((i, weight))
                nnz += 1

        self._postings = postings
        self._built = True
        logger.info("BM25 index built: %d docs, %d terms, %d nnz in %.3fs",
                     n_docs, n_terms, nnz, time.time() - t0)

    def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Return [(skill_id, score), ...] sorted by descending score."""
        if not self._built:
            return []

        tokens = tokenize(query)
        seen: set[int] = set()
        scores: dict[int, float] = {}
        for t in tokens:
            tid = self._vocab.get(t)
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            for doc_idx, weight in self._postings.get(tid, ()):
                scores[doc_idx] = scores.get(doc_idx, 0.0) + weight

        if not scores:
            return []

        # Sort by descending score, break ties by ascending doc index.
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        results = [
            (self._corpus_ids[idx], score)
            for idx, score in ranked[:top_k]
            if score > 0
        ]
        return results


# ─── Singleton index ─────────────────────────────────────────────────────────

_indexes_by_home: dict[str, BM25Index] = {}
_skills_by_home_and_id: dict[str, dict[str, dict]] = {}
_index: BM25Index | None = None
_skills_by_id: dict[str, dict] = {}


def get_index() -> BM25Index | None:
    global _index, _skills_by_id
    if _runtime_paths_are_overridden():
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

    home_key = str(get_hermes_home().expanduser().resolve(strict=False))
    if home_key in _indexes_by_home:
        return _indexes_by_home[home_key]

    skills = load_active_skills()
    if not skills:
        logger.warning("No active skills found for BM25 index")
        return None

    index = BM25Index()
    index.build(
        [s["skill_id"] for s in skills],
        [s["text"] for s in skills],
    )
    _indexes_by_home[home_key] = index
    _skills_by_home_and_id[home_key] = {s["skill_id"]: s for s in skills}
    return index


def get_skill_info(skill_id: str) -> dict | None:
    if _runtime_paths_are_overridden():
        return _skills_by_id.get(skill_id)
    home_key = str(get_hermes_home().expanduser().resolve(strict=False))
    return _skills_by_home_and_id.get(home_key, {}).get(skill_id)