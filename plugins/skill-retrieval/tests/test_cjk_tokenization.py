"""CJK tokenization and _parse_skill_md return-shape regression tests."""

import bm25_retriever as br


def test_parse_skill_md_always_returns_3_tuple(tmp_path):
    """Every exit path returns (name, description, body_preview).

    The early returns (no frontmatter / malformed YAML / unreadable file) once
    returned a 2-tuple, so a caller unpacking three values blew up on the first
    malformed SKILL.md in a real corpus.
    """
    cases = {
        "no_frontmatter.md": "# Title only\n",
        "bad_yaml.md": "---\nname: [unclosed\n---\nbody\n",
        "missing_keys.md": "---\nfoo: bar\n---\nbody\n",
        "ok.md": "---\nname: demo\ndescription: Demo skill\n---\n\u4e2d\u6587\u6b63\u6587\n",
    }
    for filename, content in cases.items():
        f = tmp_path / filename
        f.write_text(content, encoding="utf-8")
        result = br._parse_skill_md(f)
        assert isinstance(result, tuple) and len(result) == 3, (filename, result)

    missing = tmp_path / "does_not_exist.md"
    assert len(br._parse_skill_md(missing)) == 3


def test_parse_skill_md_indexes_chinese_body(tmp_path):
    f = tmp_path / "demo.md"
    f.write_text("---\nname: demo\ndescription: English only\n---\n\u53bb AI \u5473\u4fee\u6539\u5bf9\u767d\n", encoding="utf-8")
    name, desc, body = br._parse_skill_md(f)
    assert name == "demo" and desc == "English only"
    assert "\u53bb AI \u5473" in body


def test_tokenize_emits_cjk_bigrams():
    toks = br.tokenize("\u53bbAI\u5473\u4fee\u6539\u5bf9\u767d")
    assert "\u53bbai" in toks or any("ai" in t for t in toks)
    # 两个汉字以上的中文串必须产出 bigram，否则整句变成一个 token 无法匹配
    assert "\u4fee\u6539" in toks and "\u5bf9\u767d" in toks


def test_tokenize_emits_2char_cjk_token_once():
    """A 2-character CJK token IS its own bigram; it must be emitted exactly
    once. Emitting the token and its bigram appends the same string twice and
    double-counts its TF in documents and queries."""
    assert br.tokenize("对白") == ["对白"]


def test_record_skill_joins_body_preview():
    """The primary (Hermes-scan) corpus path documents name: desc + triggers +
    tags + body preview. Without the preview the CJK bigram tokenizer has no
    Chinese text to match Chinese queries against (most descriptions are
    English)."""
    skills = []
    br._record_skill(skills, set(), {
        "skill_name": "demo", "frontmatter_name": "demo",
        "description": "English only",
        "_triggers": ["hook"], "_tags": ["write"],
        "_body_preview": "去 AI 味修改对白",
    })
    assert skills[0]["text"].startswith("demo: English only")
    assert "去 AI 味修改对白" in skills[0]["text"]
    # No preview → text unchanged (legacy callers never set the key).
    skills2 = []
    br._record_skill(skills2, set(), {
        "skill_name": "plain", "frontmatter_name": "plain", "description": "d",
    })
    assert skills2[0]["text"] == "plain: d"


def test_tokenize_leaves_ascii_unchanged():
    assert br.tokenize("Dialogue Polish Remove AI Tone") == [
        "dialogue", "polish", "remove", "ai", "tone"]


def test_cjk_query_hits_chinese_corpus():
    idx = br.BM25Index()
    idx.build(
        ["writing/deai", "writing/other"],
        ["\u53bb ai \u5473 \u5bf9\u767d \u6253\u78e8 \u4fee\u6539", "unrelated english text"],
    )
    hits = [sid for sid, _ in idx.retrieve("\u5e2e\u6211\u6253\u78e8\u8fd9\u6bb5\u5bf9\u767d\uff0c\u53bbAI\u5473", top_k=6)]
    assert "writing/deai" in hits
