"""BM25 skill retriever — indexes active skill descriptions and ranks them per query.

Adapted from SR-Agents (oneal2000/SR-Agents, MIT license).
Source: https://github.com/oneal2000/SR-Agents/blob/main/src/sragents/retrieve/bm25.py
Indexed lazily and cached (invalidated on skill/config changes); retrieval is
sub-millisecond for 128 skills.
"""

import inspect
import os
import re
import sys
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


# Explicit test override points for the standalone loader; None at runtime.
# Runtime code resolves paths through Hermes' official home helpers on every
# load so multiplexed/named profiles (and Hermes' context-local home override)
# never read the profile that happened to be active at import time.
SKILLS_ROOT: "Path | None" = None
PLUGINS_ROOT: "Path | None" = None
CONFIG_PATH: "Path | None" = None

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
        # Normalize to forward slashes: on Windows str(Path) yields
        # backslashes, which break skill_id lookups and cross-platform tests.
        rel_parts = skill_dir.relative_to(root).parts
        rel_name = prefix + "/".join(rel_parts)
        leaf_name = skill_dir.name
        out.append((skill_md, rel_name, leaf_name))
    return out


def _runtime_paths_are_overridden() -> bool:
    """Return True when tests explicitly set the legacy path constants.

    Only an explicit (non-None) ``SKILLS_ROOT`` / ``CONFIG_PATH`` counts; a
    Hermes home change is a profile switch, not a test override.
    ``PLUGINS_ROOT`` is *not* a signal: Hermes-discovery tests (and Issue #8
    registry tests) patch ``get_plugins_dir`` while still wanting the
    registry-aware loader.
    """
    return SKILLS_ROOT is not None or CONFIG_PATH is not None


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
        "frontmatter_name": str(entry.get("frontmatter_name") or name),
        "description": desc,
        "text": f"{name}: {desc}",
    })


def _try_list_plugin_skill_metadata():
    """Return ``(metadata, plugin_manager)`` from Hermes' live registry, or None.

    None means the registry is unreachable and the caller should fall back to
    a raw directory scan so the corpus never silently empties.

    ``discover_plugins`` may import installed plugin packages, which insert
    their ``scripts/`` dirs onto ``sys.path``. Restore the path afterwards so
    a later ``importlib.reload(bm25_retriever)`` still finds *this* file
    rather than an older copy under ``~/.hermes/plugins``.
    """
    saved_path = list(sys.path)
    try:
        from hermes_cli.plugins import discover_plugins, get_plugin_manager
        discover_plugins()
        pm = get_plugin_manager()
        if pm is None:
            return None
        metadata = pm.list_plugin_skill_metadata() if pm else []
        return list(metadata or []), pm
    except Exception as exc:
        logger.debug("Plugin skill registry unavailable: %s", exc)
        return None
    finally:
        sys.path[:] = saved_path


def _index_cache_key(
    home_key: str,
    available_tools: "set[str] | None",
    available_toolsets: "set[str] | None",
    platform_hint: "str | None" = None,
    disabled: "frozenset[str] | None" = None,
):
    """Cache key for a BM25 index.

    The corpus also depends on the session platform (``platform_disabled``
    and ``session_platforms`` gates), so the platform hint and the resolved
    disabled set are part of the key, mirroring Hermes' own skills prompt
    cache key. Fail-open with no platform/disabled info stays a plain home
    string.
    """
    if available_tools is None and available_toolsets is None and not platform_hint and not disabled:
        return home_key
    return (
        home_key,
        frozenset(available_tools or ()),
        frozenset(available_toolsets or ()),
        platform_hint or None,
        disabled or frozenset(),
    )


def _session_platform_key_parts() -> "tuple[str | None, frozenset[str] | None]":
    """Return ``(platform_hint, frozenset(disabled))`` for the index cache key.

    Same inputs ``load_active_skills`` gates on. Never raises: any failure
    degrades that part to None (the key then matches the loader's own
    fail-open behavior as closely as the host allows).
    """
    try:
        from agent.prompt_builder import _current_session_platform_hint
        from agent.skill_utils import get_disabled_skill_names
    except Exception:
        return None, None
    try:
        platform_hint = _current_session_platform_hint() or None
    except Exception:
        platform_hint = None
    try:
        disabled = frozenset(get_disabled_skill_names(platform_hint) or ())
    except Exception:
        disabled = None
    return platform_hint, disabled


def _runtime_cache_key(
    available_tools: "set[str] | None",
    available_toolsets: "set[str] | None",
):
    """Runtime cache key shared by ``get_index`` and ``get_skill_info``."""
    home_key = str(get_hermes_home().expanduser().resolve(strict=False))
    platform_hint, disabled = _session_platform_key_parts()
    return home_key, _index_cache_key(
        home_key, available_tools, available_toolsets, platform_hint, disabled,
    )


def _load_active_skills_legacy() -> list[dict]:
    """Standalone loader: explicit test overrides, or no Hermes helpers.

    Unset path constants resolve from the current Hermes home at call time.
    """
    import yaml

    skills_root = SKILLS_ROOT if SKILLS_ROOT is not None else get_skills_dir()
    plugins_root = PLUGINS_ROOT if PLUGINS_ROOT is not None else get_plugins_dir()
    config_path = CONFIG_PATH if CONFIG_PATH is not None else get_config_path()

    # Load disabled list and profile-configured external skill directories.
    disabled = set()
    if config_path.exists():
        # A malformed or unreadable config must not abort the index build —
        # that would leave the agent with a compacted prompt and no retrieval.
        try:
            config = yaml.safe_load(config_path.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning(
                "Cannot read %s: %s — treating no skills as disabled",
                config_path, exc,
            )
            config = {}
        if not isinstance(config, dict):
            config = {}
        skills_cfg = config.get("skills")
        if isinstance(skills_cfg, dict):
            disabled = set(skills_cfg.get("disabled") or [])

    # Collect candidate skill files from both roots.
    candidates: list[tuple[Path, str, str]] = []
    candidates += _iter_skill_files(skills_root)
    if plugins_root.exists():
        for plugin_dir in sorted(plugins_root.iterdir()):
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


def load_active_skills(
    available_tools: "set[str] | None" = None,
    available_toolsets: "set[str] | None" = None,
) -> list[dict]:
    """Load active skills using Hermes' own profile-aware discovery helpers.

    Runtime path/config resolution is delegated to Hermes core helpers so named
    profiles, context-local home overrides, ``skills.external_dirs``, trusted
    project-local skills, disabled lists, platform gates, and condition gates
    match the agent's normal skill index as closely as a plugin can. Plugin-
    bundled skills come from Hermes' plugin registry when available, with a
    directory-scan fallback so the corpus never silently empties.

    ``available_tools`` / ``available_toolsets`` are forwarded to
    ``_skill_should_show``. Both default to None, which is Hermes' fail-open
    (index everything) when the session's capability snapshot is unknown.
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

    # Compat shim for Hermes ≤0.20.x, where _skill_should_show takes 3
    # positional arguments (no session_platform). plugin.yaml now requires
    # >=0.21.1 (4-arg), but the shim is kept for hosts that skip the
    # requires_hermes gate. Wrap the
    # 3-arg host function in a 4-arg adapter once, at load time, by
    # inspecting its declared parameters. Fall back to assuming the
    # 4-arg form when inspection fails, because the shim must not mask
    # a real TypeError from a future signature change.
    _show_params = None
    try:
        _show_params = inspect.signature(_skill_should_show).parameters
    except (TypeError, ValueError):
        _show_params = None
    if _show_params is not None and len(_show_params) < 4:
        _raw_should_show = _skill_should_show

        def _skill_should_show(  # noqa: F811 - deliberate host-function wrapper
            conditions, available_tools, available_toolsets, session_platform=None,
        ):
            return _raw_should_show(conditions, available_tools, available_toolsets)

    platform_hint = _current_session_platform_hint() or None
    disabled = get_disabled_skill_names(platform_hint)
    skills: list[dict] = []
    seen_names: set[str] = set()
    skill_matches_platform = getattr(
        sys.modules.get("agent.skill_utils"), "skill_matches_platform", lambda _fm: True,
    )

    def add_skill_file(
        skill_file: Path, root: Path, *, prefix: str = "", qualify_name: bool = False,
    ) -> None:
        try:
            is_compatible, frontmatter, desc = _parse_skill_file(skill_file)
            if not is_compatible:
                return
            entry = _build_snapshot_entry(skill_file, root, frontmatter, desc)
            if entry["frontmatter_name"] in disabled or entry["skill_name"] in disabled:
                return
            if not _skill_should_show(
                extract_skill_conditions(frontmatter),
                available_tools,
                available_toolsets,
                platform_hint,
            ):
                return
            if qualify_name and prefix:
                qname = f"{prefix}{entry['frontmatter_name']}"
                entry = dict(entry)
                entry["frontmatter_name"] = qname
                entry["skill_name"] = qname
                prefix = ""
            _record_skill(skills, seen_names, entry, prefix=prefix)
        except Exception as exc:
            logger.debug("Error reading skill %s: %s", skill_file, exc)

    def scan_plugin_directories(*, qualify_name: bool) -> None:
        plugins_root = get_plugins_dir()
        if not plugins_root.exists():
            return
        for plugin_dir in sorted(plugins_root.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            plugin_skills = plugin_dir / "skills"
            if not plugin_skills.is_dir():
                continue
            for skill_file in iter_skill_index_files(plugin_skills, "SKILL.md"):
                add_skill_file(
                    skill_file, plugin_skills,
                    prefix=f"{plugin_dir.name}:",
                    qualify_name=qualify_name,
                )

    def add_registry_plugin_skill(plugin_skill: dict, pm) -> None:
        plugin_skill = dict(plugin_skill)
        frontmatter = dict(plugin_skill.pop("frontmatter", {}) or {})
        qualified = str(plugin_skill.get("name") or "").strip()
        if not qualified:
            return
        desc = str(plugin_skill.get("description") or "")
        # Parse on-disk SKILL.md before platform/disabled/capability gates so
        # gating uses file frontmatter. Registry metadata is the fallback when
        # the file cannot be resolved or read.
        skill_path = plugin_skill.get("path")
        finder = getattr(pm, "find_plugin_skill", None) if pm is not None else None
        if skill_path is None and callable(finder):
            try:
                skill_path = finder(qualified)
            except Exception as exc:
                logger.debug("find_plugin_skill(%s) failed: %s", qualified, exc)
                skill_path = None
        if skill_path:
            try:
                path_obj = Path(skill_path)
                if path_obj.is_file():
                    _ok, file_fm, file_desc = _parse_skill_file(path_obj)
                    if file_desc:
                        desc = file_desc
                    if file_fm:
                        frontmatter = file_fm
            except Exception as exc:
                logger.debug("Error reading registry skill %s: %s", skill_path, exc)
        try:
            if not skill_matches_platform(frontmatter):
                return
        except Exception as exc:
            logger.debug("skill_matches_platform failed for %s: %s", qualified, exc)
        bare = str(
            frontmatter.get("name")
            or plugin_skill.get("bare_name")
            or qualified.split(":")[-1]
        )
        if qualified in disabled or bare in disabled:
            return
        if not _skill_should_show(
            extract_skill_conditions(frontmatter),
            available_tools,
            available_toolsets,
            platform_hint,
        ):
            return
        entry = {
            "category": "general",
            "skill_name": qualified,
            "frontmatter_name": qualified,
            "description": desc,
        }
        _record_skill(skills, seen_names, entry)

    # Precedence mirrors Hermes: trusted project-local → profile-local →
    # configured external dirs. First seen name wins.
    for project_dir in get_project_skills_dirs():
        for skill_file in iter_project_skill_files(project_dir):
            add_skill_file(skill_file, project_dir)

    all_skill_dirs = list(get_all_skills_dirs() or [])
    for skill_root in all_skill_dirs:
        for skill_file in iter_skill_index_files(skill_root, "SKILL.md"):
            add_skill_file(skill_file, skill_root)

    registry = _try_list_plugin_skill_metadata()
    if registry is not None:
        metadata, pm = registry
        for plugin_skill in metadata:
            if isinstance(plugin_skill, dict):
                add_registry_plugin_skill(plugin_skill, pm)
    else:
        scan_plugin_directories(qualify_name=True)

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

        # Lucene BM25 IDF: log(1 + (N - df + 0.5) / (df + 0.5)). Always > 0, so
        # terms in >= half the docs (and 1-2 doc corpora) still score.
        idf: dict[int, float] = {}
        for tid, df_count in df.items():
            idf[tid] = math.log(1.0 + (n_docs - df_count + 0.5) / (df_count + 0.5))

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

# Bounded caches: distinct (home × capability-snapshot) combinations could grow
# without limit in long-lived processes; evict the oldest snapshot per home
# beyond the cap so stale snapshots cannot accumulate.
_MAX_CACHED_CAP_KEYS_PER_HOME = 8

_indexes_by_home: dict = {}
_skills_by_home_and_id: dict = {}
_cap_key_order_by_home: dict = {}
_index: BM25Index | None = None
_skills_by_id: dict[str, dict] = {}
# Runtime-override (legacy-test) caches keyed by capability snapshot. The
# zero-arg path keeps using ``_index`` / ``_skills_by_id`` exactly as before.
_override_indexes_by_cap: dict = {}
_override_skills_by_cap: dict = {}
# Runtime entries are validated against a cheap on-disk manifest (see
# _corpus_manifest) so skills added/removed or config edits made outside this
# process are picked up without a restart. An empty corpus is cached too
# (value None) so zero-skill installs don't rescan every root each turn.
_manifest_by_key: dict = {}
_warned_empty_keys: set = set()


def clear_index_cache() -> None:
    """Drop every cached BM25 index and skill-info map.

    Called from the plugin's wrapper around Hermes'
    ``clear_skills_system_prompt_cache`` (skill_manage create/patch, hub
    install, ``/skills`` toggles), so the next turn rebuilds the corpus.
    """
    global _index, _skills_by_id
    _indexes_by_home.clear()
    _skills_by_home_and_id.clear()
    _cap_key_order_by_home.clear()
    _manifest_by_key.clear()
    _warned_empty_keys.clear()
    _override_indexes_by_cap.clear()
    _override_skills_by_cap.clear()
    _index = None
    _skills_by_id = {}


def _stat_signature(path: str) -> "tuple[int, int] | None":
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _corpus_manifest() -> "tuple | None":
    """Cheap signature of the on-disk inputs to the runtime corpus.

    Covers each skills root and plugin ``skills/`` dir, their immediate
    children (category dirs / flat skill dirs) and those children's
    ``SKILL.md``, plus config.yaml (mtime_ns, size). Adding or removing a
    skill changes a root or category dir mtime; a content-only edit of a
    nested SKILL.md is left to the ``clear_skills_system_prompt_cache``
    hook. Returns None when the manifest cannot be computed (the cache is
    then trusted as before); never raises.
    """
    try:
        roots: list[str] = []
        try:
            from agent.skill_utils import get_all_skills_dirs, get_project_skills_dirs
            roots += [str(d) for d in (get_project_skills_dirs() or [])]
            roots += [str(d) for d in (get_all_skills_dirs() or [])]
        except Exception:
            roots.append(str(get_skills_dir()))
        plugins_root = str(get_plugins_dir())
        entries: list = [("config", _stat_signature(str(get_config_path())))]
        entries.append((plugins_root, _stat_signature(plugins_root)))
        try:
            with os.scandir(plugins_root) as it:
                roots += sorted(
                    os.path.join(e.path, "skills") for e in it if e.is_dir()
                )
        except OSError:
            pass
        for root in roots:
            entries.append((root, _stat_signature(root)))
            try:
                with os.scandir(root) as it:
                    children = sorted(e.path for e in it if e.is_dir())
            except OSError:
                continue
            for child in children:
                entries.append((child, _stat_signature(child)))
                skill_md = os.path.join(child, "SKILL.md")
                entries.append((skill_md, _stat_signature(skill_md)))
        return tuple(entries)
    except Exception as exc:
        logger.debug("Skill corpus manifest unavailable: %s", exc)
        return None


def _load_active_skills_for_index(
    available_tools: "set[str] | None",
    available_toolsets: "set[str] | None",
) -> list[dict]:
    """Call ``load_active_skills`` without kwargs when both snapshots are unknown.

    Existing tests monkeypatch ``load_active_skills`` with a zero-arg fake;
    fail-open ``get_index()`` must keep calling it that way.
    """
    if available_tools is None and available_toolsets is None:
        return load_active_skills()
    return load_active_skills(
        available_tools=available_tools, available_toolsets=available_toolsets,
    )


def get_index(
    available_tools: "set[str] | None" = None,
    available_toolsets: "set[str] | None" = None,
) -> BM25Index | None:
    global _index, _skills_by_id
    if _runtime_paths_are_overridden():
        if available_tools is None and available_toolsets is None:
            if _index is not None:
                return _index
            skills = _load_active_skills_for_index(available_tools, available_toolsets)
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
        cap_key = _index_cache_key("", available_tools, available_toolsets)
        cached = _override_indexes_by_cap.get(cap_key)
        if cached is not None:
            return cached
        skills = _load_active_skills_for_index(available_tools, available_toolsets)
        if not skills:
            logger.warning("No active skills found for BM25 index")
            return None
        index = BM25Index()
        index.build(
            [s["skill_id"] for s in skills],
            [s["text"] for s in skills],
        )
        _override_indexes_by_cap[cap_key] = index
        _override_skills_by_cap[cap_key] = {s["skill_id"]: s for s in skills}
        return index

    home_key, cache_key = _runtime_cache_key(available_tools, available_toolsets)
    manifest = _corpus_manifest()
    if cache_key in _indexes_by_home and _manifest_by_key.get(cache_key) == manifest:
        return _indexes_by_home[cache_key]

    skills = _load_active_skills_for_index(available_tools, available_toolsets)
    index = None
    if skills:
        _warned_empty_keys.discard(cache_key)
        index = BM25Index()
        index.build(
            [s["skill_id"] for s in skills],
            [s["text"] for s in skills],
        )
    elif cache_key not in _warned_empty_keys:
        _warned_empty_keys.add(cache_key)
        logger.warning("No active skills found for BM25 index")
    _indexes_by_home[cache_key] = index
    _skills_by_home_and_id[cache_key] = {s["skill_id"]: s for s in skills}
    _manifest_by_key[cache_key] = manifest
    order = _cap_key_order_by_home.setdefault(home_key, [])
    if cache_key not in order:
        order.append(cache_key)
    if len(order) > _MAX_CACHED_CAP_KEYS_PER_HOME:
        stale = order[:-_MAX_CACHED_CAP_KEYS_PER_HOME]
        _cap_key_order_by_home[home_key] = order[-_MAX_CACHED_CAP_KEYS_PER_HOME:]
        for key in stale:
            _indexes_by_home.pop(key, None)
            _skills_by_home_and_id.pop(key, None)
            _manifest_by_key.pop(key, None)
            _warned_empty_keys.discard(key)
    return index


def get_skill_info(
    skill_id: str,
    available_tools: "set[str] | None" = None,
    available_toolsets: "set[str] | None" = None,
) -> dict | None:
    if _runtime_paths_are_overridden():
        if available_tools is None and available_toolsets is None:
            return _skills_by_id.get(skill_id)
        cap_key = _index_cache_key("", available_tools, available_toolsets)
        return _override_skills_by_cap.get(cap_key, {}).get(skill_id)
    _home_key, cache_key = _runtime_cache_key(available_tools, available_toolsets)
    return _skills_by_home_and_id.get(cache_key, {}).get(skill_id)