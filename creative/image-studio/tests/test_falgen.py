#!/usr/bin/env python3
"""Unit tests for falgen.py pure-Python helpers and dry-run behavior.

Run:  python -m pytest creative/image-studio/tests/test_falgen.py -v
  or:  python creative/image-studio/tests/test_falgen.py
"""

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import falgen  # noqa: E402


class TestAspectArgs(unittest.TestCase):
    def test_flux_aspect_maps_to_image_size(self):
        self.assertEqual(
            falgen._aspect_args("fal-ai/flux/schnell", "16:9"),
            {"image_size": "landscape_16_9"},
        )

    def test_nano_banana_aspect_maps_to_aspect_ratio(self):
        self.assertEqual(
            falgen._aspect_args("fal-ai/nano-banana-pro", "4:3"),
            {"aspect_ratio": "4:3"},
        )

    def test_kontext_ignores_aspect(self):
        self.assertEqual(falgen._aspect_args("fal-ai/flux-kontext/dev", "16:9"), {})


class TestComputeCost(unittest.TestCase):
    def test_per_image_basic(self):
        cost, currency, basis, exact = falgen._compute_cost(
            "fal-ai/nano-banana-pro",
            (0.15, "image", "USD"),
            [{"path": "a.png"}, {"path": "b.png"}],
            {},
        )
        self.assertAlmostEqual(cost, 0.30, places=4)
        self.assertEqual(currency, "USD")
        self.assertTrue(exact)
        self.assertIn("2 x", basis)

    def test_nano_banana_4k_multiplier(self):
        cost, _currency, basis, exact = falgen._compute_cost(
            "fal-ai/nano-banana-pro/edit",
            (0.15, "image", "USD"),
            [{"path": "a.png"}],
            {"resolution": "4K"},
        )
        self.assertAlmostEqual(cost, 0.30, places=4)
        self.assertFalse(exact)
        self.assertIn("4K", basis)

    def test_megapixel_estimate(self):
        cost, _currency, basis, exact = falgen._compute_cost(
            "fal-ai/clarity-upscaler",
            (0.03, "megapixel", "USD"),
            [{"path": "a.png", "w": 2000, "h": 1000}],
            {},
        )
        self.assertAlmostEqual(cost, 0.06, places=4)
        self.assertFalse(exact)
        self.assertIn("2.00 MP", basis)


class TestArgParsing(unittest.TestCase):
    def test_parse_scalar_json_bool_number_and_string(self):
        self.assertEqual(falgen._parse_scalar('{"k": 1}'), {"k": 1})
        self.assertIs(falgen._parse_scalar("true"), True)
        self.assertEqual(falgen._parse_scalar("42"), 42)
        self.assertEqual(falgen._parse_scalar("soft light"), "soft light")

    def test_parse_extra_args(self):
        self.assertEqual(
            falgen._parse_extra_args(["seed=42", "negative_prompt=blurry"], ['{"resolution":"4K"}']),
            {"resolution": "4K", "seed": 42, "negative_prompt": "blurry"},
        )

    def test_parse_extra_args_requires_equals(self):
        with self.assertRaises(SystemExit):
            falgen._parse_extra_args(["badarg"])


class TestDryRun(unittest.TestCase):
    def test_generate_dry_run_does_not_require_fal_key(self):
        args = argparse.Namespace(
            prompt="a test image",
            aspect="16:9",
            num=2,
            seed=None,
            model=None,
            out_dir="_workings",
            name="image",
            arg=None,
            arg_json=None,
            cost_log=None,
            run_log=None,
            verbose=False,
            dry_run=True,
        )
        with patch.dict(os.environ, {}, clear=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                falgen.cmd_generate(args)
        out = buf.getvalue()
        self.assertIn("DRY RUN", out)
        self.assertIn("fal-ai/flux/schnell", out)
        self.assertIn("no fal.ai call", out)

    def test_kontext_multi_image_rejected_before_call(self):
        args = argparse.Namespace(
            prompt="edit",
            image=["a.png", "b.png"],
            aspect=None,
            num=1,
            seed=None,
            model="fal-ai/flux-kontext/dev",
            out_dir="_workings",
            name="image_edit",
            arg=None,
            arg_json=None,
            cost_log=None,
            run_log=None,
            verbose=False,
            dry_run=True,
        )
        with self.assertRaises(SystemExit):
            falgen.cmd_edit(args)


class TestExtractFalKey(unittest.TestCase):
    """Tests for _extract_fal_key — content-based key detection from file text."""

    SAMPLE_KEY = "a1b2c3d4-e5f6-7890-abcd-ef1234567890:abcdef0123456789abcdef0123456789"

    def test_fal_key_equals_assignment(self):
        text = f"FAL_KEY={self.SAMPLE_KEY}"
        self.assertEqual(falgen._extract_fal_key(text), self.SAMPLE_KEY)

    def test_fal_key_colon_assignment(self):
        text = f"FAL_KEY: {self.SAMPLE_KEY}"
        self.assertEqual(falgen._extract_fal_key(text), self.SAMPLE_KEY)

    def test_fal_key_quoted(self):
        text = f'FAL_KEY="{self.SAMPLE_KEY}"'
        self.assertEqual(falgen._extract_fal_key(text), self.SAMPLE_KEY)

    def test_fal_key_in_multiline_file(self):
        text = f"# my keys\nFAL_KEY={self.SAMPLE_KEY}\nOTHER=xyz\n"
        self.assertEqual(falgen._extract_fal_key(text), self.SAMPLE_KEY)

    def test_bare_id_secret_pattern(self):
        """A raw id:secret UUID token anywhere in text is detected."""
        text = f"some preamble\n{self.SAMPLE_KEY}\nmore stuff"
        self.assertEqual(falgen._extract_fal_key(text), self.SAMPLE_KEY)

    def test_fal_key_assignment_takes_priority_over_bare_token(self):
        """If both a FAL_KEY= line and a bare token exist, the assignment wins."""
        bare = "00000000-0000-0000-0000-000000000000:0000000000000000000000000000000000"
        text = f"FAL_KEY={self.SAMPLE_KEY}\nalso here: {bare}"
        self.assertEqual(falgen._extract_fal_key(text), self.SAMPLE_KEY)

    def test_name_hinted_returns_stripped_single_line(self):
        """For a file whose name hints fal/key, a bare single-line token is accepted."""
        token = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:0123456789abcdef0123456789abcdef"
        self.assertEqual(falgen._extract_fal_key(token, name_hinted=True), token)

    def test_name_hinted_rejects_multiline(self):
        text = "line one\nline two\n"
        self.assertIsNone(falgen._extract_fal_key(text, name_hinted=True))

    def test_name_hinted_rejects_no_colon(self):
        self.assertIsNone(falgen._extract_fal_key("just-a-string", name_hinted=True))

    def test_name_hinted_rejects_too_short(self):
        self.assertIsNone(falgen._extract_fal_key("ab:cd", name_hinted=True))

    def test_name_hinted_rejects_with_spaces(self):
        self.assertIsNone(falgen._extract_fal_key("a b c d e f : x y z", name_hinted=True))

    def test_no_match_returns_none(self):
        self.assertIsNone(falgen._extract_fal_key("nothing useful here"))

    def test_no_match_name_hinted_returns_none(self):
        self.assertIsNone(falgen._extract_fal_key("nothing useful", name_hinted=True))


class TestAutoloadFalKeys(unittest.TestCase):
    """Tests for _autoload_fal_keys — env-var-wins, then cwd, then home, by content."""

    SAMPLE_KEY = "a1b2c3d4-e5f6-7890-abcd-ef1234567890:abcdef0123456789abcdef0123456789"
    ADMIN_KEY = "11111111-2222-3333-4444-555555555555:fedcba9876543210fedcba9876543210"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_cwd = Path.cwd()
        self._orig_home = os.environ.get("HOME")

    def tearDown(self):
        os.chdir(str(self._orig_cwd))
        os.environ.pop("FAL_KEY", None)
        os.environ.pop("FAL_ADMIN_KEY", None)
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        else:
            os.environ.pop("HOME", None)
        self._tmp.cleanup()

    def _set_cwd(self, path):
        os.chdir(str(path))

    def _set_home(self, path):
        os.environ["HOME"] = str(path)

    def test_env_var_wins_over_file(self):
        """If FAL_KEY is already in env, no file is read."""
        d = Path(self._tmp.name) / "work"
        d.mkdir()
        (d / "fal key.txt").write_text(f"FAL_KEY={self.SAMPLE_KEY}")
        self._set_cwd(d)
        with patch.dict(os.environ, {"FAL_KEY": "env-var-key"}, clear=False):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ["FAL_KEY"], "env-var-key")

    def test_finds_key_in_cwd_file(self):
        d = Path(self._tmp.name) / "work"
        d.mkdir()
        (d / "fal key.txt").write_text(f"FAL_KEY={self.SAMPLE_KEY}")
        self._set_cwd(d)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        self._set_home(home)
        env = {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}
        with patch.dict(os.environ, env, clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ["FAL_KEY"], self.SAMPLE_KEY)

    def test_finds_bare_id_secret_in_cwd(self):
        d = Path(self._tmp.name) / "work"
        d.mkdir()
        (d / "notes.txt").write_text(f"my key is {self.SAMPLE_KEY}")
        self._set_cwd(d)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        self._set_home(home)
        env = {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}
        with patch.dict(os.environ, env, clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ["FAL_KEY"], self.SAMPLE_KEY)

    def test_finds_key_in_home_when_cwd_empty(self):
        work = Path(self._tmp.name) / "work"
        work.mkdir()
        self._set_cwd(work)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        (home / "fal key.txt").write_text(f"FAL_KEY={self.SAMPLE_KEY}")
        self._set_home(home)
        # Keep HOME in env so Path.home() resolves; only clear FAL_KEY/FAL_ADMIN_KEY
        env = {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}
        with patch.dict(os.environ, env, clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ["FAL_KEY"], self.SAMPLE_KEY)

    def test_skips_large_files(self):
        """Files >100KB are skipped."""
        d = Path(self._tmp.name) / "work"
        d.mkdir()
        big = d / "fal key.txt"
        big.write_text(f"FAL_KEY={self.SAMPLE_KEY}\n" + "x" * 110_000)
        self._set_cwd(d)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        self._set_home(home)
        env = {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}
        with patch.dict(os.environ, env, clear=True):
            falgen._autoload_fal_keys()
            self.assertNotIn("FAL_KEY", os.environ)

    def test_picks_up_admin_key_too(self):
        d = Path(self._tmp.name) / "work"
        d.mkdir()
        (d / "keys.txt").write_text(
            f"FAL_KEY={self.SAMPLE_KEY}\nFAL_ADMIN_KEY={self.ADMIN_KEY}"
        )
        self._set_cwd(d)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        self._set_home(home)
        env = {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}
        with patch.dict(os.environ, env, clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ["FAL_KEY"], self.SAMPLE_KEY)
            self.assertEqual(os.environ["FAL_ADMIN_KEY"], self.ADMIN_KEY)

    def test_no_key_found_leaves_env_unset(self):
        d = Path(self._tmp.name) / "work"
        d.mkdir()
        (d / "random.txt").write_text("nothing useful")
        self._set_cwd(d)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        self._set_home(home)
        env = {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}
        with patch.dict(os.environ, env, clear=True):
            falgen._autoload_fal_keys()
            self.assertNotIn("FAL_KEY", os.environ)


class TestSearchModels(unittest.TestCase):
    """Tests for _search_models — live catalogue search with mock HTTP."""

    def _mock_response(self, models, status=200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {"models": models}
        return resp

    def test_returns_models_on_success(self):
        models = [
            {"endpoint_id": "fal-ai/test-1", "metadata": {
                "display_name": "Test 1", "category": "text-to-image",
                "license_type": "MIT", "description": "desc", "status": "active",
            }},
        ]
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response(models)
        result = falgen._search_models("test", requests_mod)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["endpoint_id"], "fal-ai/test-1")
        self.assertEqual(result[0]["name"], "Test 1")

    def test_filters_inactive_models(self):
        models = [
            {"endpoint_id": "fal-ai/active", "metadata": {"status": "active"}},
            {"endpoint_id": "fal-ai/inactive", "metadata": {"status": "deprecated"}},
        ]
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response(models)
        result = falgen._search_models("test", requests_mod)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["endpoint_id"], "fal-ai/active")

    def test_category_filter(self):
        models = [
            {"endpoint_id": "fal-ai/a", "metadata": {"category": "text-to-image", "status": "active"}},
            {"endpoint_id": "fal-ai/b", "metadata": {"category": "image-to-image", "status": "active"}},
        ]
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response(models)
        result = falgen._search_models("test", requests_mod, category="text-to-image")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["endpoint_id"], "fal-ai/a")

    def test_limit_respected(self):
        models = [
            {"endpoint_id": f"fal-ai/m{i}", "metadata": {"status": "active"}}
            for i in range(10)
        ]
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response(models)
        result = falgen._search_models("test", requests_mod, limit=3)
        self.assertEqual(len(result), 3)

    def test_non_200_returns_empty(self):
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response([], status=403)
        result = falgen._search_models("test", requests_mod)
        self.assertEqual(result, [])

    def test_exception_returns_empty(self):
        requests_mod = MagicMock()
        requests_mod.get.side_effect = ConnectionError("boom")
        result = falgen._search_models("test", requests_mod)
        self.assertEqual(result, [])


class TestPricesBatch(unittest.TestCase):
    """Tests for _prices_batch — batch pricing lookup with mock HTTP."""

    def _mock_response(self, prices, status=200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {"prices": prices}
        return resp

    def test_returns_price_map_on_success(self):
        prices = [
            {"endpoint_id": "fal-ai/a", "unit_price": 0.04, "unit": "image"},
            {"endpoint_id": "fal-ai/b", "unit_price": 0.01, "unit": "second"},
        ]
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response(prices)
        result = falgen._prices_batch(["fal-ai/a", "fal-ai/b"], requests_mod)
        self.assertEqual(result["fal-ai/a"], (0.04, "image"))
        self.assertEqual(result["fal-ai/b"], (0.01, "second"))

    def test_deduplicates_endpoint_ids(self):
        prices = [{"endpoint_id": "fal-ai/a", "unit_price": 0.04, "unit": "image"}]
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response(prices)
        result = falgen._prices_batch(["fal-ai/a", "fal-ai/a", ""], requests_mod)
        self.assertEqual(len(result), 1)

    def test_empty_input_returns_empty(self):
        requests_mod = MagicMock()
        result = falgen._prices_batch([], requests_mod)
        self.assertEqual(result, {})
        requests_mod.get.assert_not_called()

    def test_non_200_returns_empty(self):
        requests_mod = MagicMock()
        requests_mod.get.return_value = self._mock_response([], status=500)
        result = falgen._prices_batch(["fal-ai/a"], requests_mod)
        self.assertEqual(result, {})

    def test_exception_returns_empty(self):
        requests_mod = MagicMock()
        requests_mod.get.side_effect = TimeoutError("slow")
        result = falgen._prices_batch(["fal-ai/a"], requests_mod)
        self.assertEqual(result, {})


class TestPriceStr(unittest.TestCase):
    """Tests for _price_str — pure formatting helper."""

    def test_with_price(self):
        self.assertEqual(falgen._price_str((0.04, "image")), "$0.04/image")

    def test_none(self):
        self.assertEqual(falgen._price_str(None), "price n/a")

    def test_none_unit_price(self):
        self.assertEqual(falgen._price_str((None, "image")), "price n/a")


class TestCmdSearch(unittest.TestCase):
    """Tests for cmd_search — output formatting with mocked deps."""

    def setUp(self):
        self._fal_client = MagicMock()
        self._requests = MagicMock()

    def _patch_deps(self):
        return patch.object(falgen, "_import_deps", return_value=(self._fal_client, self._requests))

    def _patch_key(self):
        return patch.dict(os.environ, {"FAL_KEY": "test-key"}, clear=False)

    def test_search_prints_results(self):
        models = [
            {"endpoint_id": "fal-ai/test-1", "metadata": {
                "display_name": "Test 1", "category": "text-to-image",
                "license_type": "MIT", "description": "A test model", "status": "active",
            }},
        ]
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"models": models}
        self._requests.get.return_value = resp

        args = argparse.Namespace(query="test", category=None, limit=15)
        with self._patch_deps(), self._patch_key():
            buf = io.StringIO()
            with redirect_stdout(buf):
                falgen.cmd_search(args)
        out = buf.getvalue()
        self.assertIn("fal-ai/test-1", out)
        self.assertIn("Test 1", out)
        self.assertIn("Default-first", out)

    def test_search_no_results_message(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"models": []}
        self._requests.get.return_value = resp

        args = argparse.Namespace(query="zzz", category=None, limit=15)
        with self._patch_deps(), self._patch_key():
            buf = io.StringIO()
            with redirect_stdout(buf):
                falgen.cmd_search(args)
        out = buf.getvalue()
        self.assertIn("No active models matched", out)
        self.assertIn("fal.ai/models", out)


class TestCmdRecommend(unittest.TestCase):
    """Tests for cmd_recommend — prints default models with live pricing."""

    def setUp(self):
        self._fal_client = MagicMock()
        self._requests = MagicMock()

    def _patch_deps(self):
        return patch.object(falgen, "_import_deps", return_value=(self._fal_client, self._requests))

    def _patch_key(self):
        return patch.dict(os.environ, {"FAL_KEY": "test-key"}, clear=False)

    def test_recommend_prints_all_defaults(self):
        # Mock pricing to return a price for each default model
        prices = [
            {"endpoint_id": mid, "unit_price": 0.01, "unit": "image"}
            for mid in falgen.DEFAULT_MODELS.values()
        ]
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"prices": prices}
        self._requests.get.return_value = resp

        args = argparse.Namespace()
        with self._patch_deps(), self._patch_key():
            buf = io.StringIO()
            with redirect_stdout(buf):
                falgen.cmd_recommend(args)
        out = buf.getvalue()
        self.assertIn("Recommended default", out)
        for stage in falgen.DEFAULT_MODELS:
            self.assertIn(stage, out)
        for mid in falgen.DEFAULT_MODELS.values():
            self.assertIn(mid, out)

    def test_recommend_with_no_pricing_shows_na(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.json.return_value = {"prices": []}
        self._requests.get.return_value = resp

        args = argparse.Namespace()
        with self._patch_deps(), self._patch_key():
            buf = io.StringIO()
            with redirect_stdout(buf):
                falgen.cmd_recommend(args)
        out = buf.getvalue()
        self.assertIn("price n/a", out)


class TestFalKeyAutoloadSecurity(unittest.TestCase):
    """Regression tests: the autoloader must never adopt another service's credential."""

    FAL_SHAPED = "a1b2c3d4-e5f6-7890-abcd-ef1234567890:abcdef0123456789abcdef0123456789"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_cwd = Path.cwd()
        self._orig_home = os.environ.get("HOME")
        self.work = Path(self._tmp.name) / "work"
        self.work.mkdir()
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()
        os.chdir(str(self.work))
        os.environ["HOME"] = str(self.home)

    def tearDown(self):
        os.chdir(str(self._orig_cwd))
        os.environ.pop("FAL_KEY", None)
        os.environ.pop("FAL_ADMIN_KEY", None)
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        else:
            os.environ.pop("HOME", None)
        self._tmp.cleanup()

    def _clean_env(self):
        return {k: v for k, v in os.environ.items() if k not in ("FAL_KEY", "FAL_ADMIN_KEY")}

    def test_whole_file_non_fal_credential_rejected(self):
        """A user:password / sid:token style secret in a hinted file must NOT become FAL_KEY."""
        (self.home / "key.txt").write_text("myuser:SuperSecretPassword123456")
        with patch.dict(os.environ, self._clean_env(), clear=True):
            falgen._autoload_fal_keys()
            self.assertNotIn("FAL_KEY", os.environ)

    def test_whole_file_fal_shaped_token_accepted_in_cwd(self):
        (self.work / "fal key.txt").write_text(self.FAL_SHAPED + "\n")
        with patch.dict(os.environ, self._clean_env(), clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ.get("FAL_KEY"), self.FAL_SHAPED)

    def test_bare_fal_shaped_token_in_home_not_adopted(self):
        """HOME is labeled-only: even a fal-shaped bare token there is ignored."""
        (self.home / "api_tokens.txt").write_text(f"some service: {self.FAL_SHAPED}\n")
        with patch.dict(os.environ, self._clean_env(), clear=True):
            falgen._autoload_fal_keys()
            self.assertNotIn("FAL_KEY", os.environ)

    def test_labeled_assignment_in_home_adopted(self):
        (self.home / "fal.env").write_text(f"FAL_KEY={self.FAL_SHAPED}\n")
        with patch.dict(os.environ, self._clean_env(), clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ.get("FAL_KEY"), self.FAL_SHAPED)

    def test_commented_assignment_ignored(self):
        """`# FAL_KEY=placeholder` in a notes file must not be loaded as a key."""
        (self.work / "notes.txt").write_text("# FAL_KEY=your-key-here\nsome notes\n")
        with patch.dict(os.environ, self._clean_env(), clear=True):
            falgen._autoload_fal_keys()
            self.assertNotIn("FAL_KEY", os.environ)

    def test_exported_assignment_accepted(self):
        (self.work / "keys.env").write_text(f"export FAL_KEY={self.FAL_SHAPED}\n")
        with patch.dict(os.environ, self._clean_env(), clear=True):
            falgen._autoload_fal_keys()
            self.assertEqual(os.environ.get("FAL_KEY"), self.FAL_SHAPED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
