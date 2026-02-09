"""Tests for model auto-downloader."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vdj_manager.analysis.model_downloader import (
    MODELS_DIR,
    EMBEDDING_MODEL,
    CLASSIFIER_MODEL,
    models_available,
    ensure_model_files,
    _ensure_single_model,
    _sha256,
)


class TestModelsAvailable:
    """Tests for models_available() check."""

    def test_returns_false_when_no_models(self, tmp_path):
        with patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path):
            assert models_available() is False

    def test_returns_false_when_only_embedding(self, tmp_path):
        (tmp_path / EMBEDDING_MODEL["filename"]).touch()
        with patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path):
            assert models_available() is False

    def test_returns_false_when_only_classifier(self, tmp_path):
        (tmp_path / CLASSIFIER_MODEL["filename"]).touch()
        with patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path):
            assert models_available() is False

    def test_returns_true_when_both_exist(self, tmp_path):
        (tmp_path / EMBEDDING_MODEL["filename"]).touch()
        (tmp_path / CLASSIFIER_MODEL["filename"]).touch()
        with patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path):
            assert models_available() is True


class TestEnsureModelFiles:
    """Tests for ensure_model_files() download logic."""

    def test_skips_download_when_files_exist(self, tmp_path):
        (tmp_path / EMBEDDING_MODEL["filename"]).write_text("fake-embedding")
        (tmp_path / CLASSIFIER_MODEL["filename"]).write_text("fake-classifier")

        with patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path):
            emb, cls = ensure_model_files()

        assert emb == tmp_path / EMBEDDING_MODEL["filename"]
        assert cls == tmp_path / CLASSIFIER_MODEL["filename"]

    def test_downloads_missing_files(self, tmp_path):
        def fake_urlretrieve(url, dest):
            Path(dest).write_text("model-data")

        with (
            patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path),
            patch(
                "vdj_manager.analysis.model_downloader.urllib.request.urlretrieve",
                side_effect=fake_urlretrieve,
            ),
        ):
            emb, cls = ensure_model_files()

        assert emb.exists()
        assert cls.exists()
        assert emb.read_text() == "model-data"
        assert cls.read_text() == "model-data"

    def test_creates_models_dir(self, tmp_path):
        models_dir = tmp_path / "subdir" / "models"

        def fake_urlretrieve(url, dest):
            Path(dest).write_text("data")

        with (
            patch("vdj_manager.analysis.model_downloader.MODELS_DIR", models_dir),
            patch(
                "vdj_manager.analysis.model_downloader.urllib.request.urlretrieve",
                side_effect=fake_urlretrieve,
            ),
        ):
            ensure_model_files()

        assert models_dir.exists()

    def test_cleans_up_temp_on_download_failure(self, tmp_path):
        with (
            patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path),
            patch(
                "vdj_manager.analysis.model_downloader.urllib.request.urlretrieve",
                side_effect=OSError("network error"),
            ),
        ):
            with pytest.raises(OSError, match="network error"):
                ensure_model_files()

        # No temp files left behind
        assert list(tmp_path.glob("*.tmp")) == []


class TestEnsureSingleModel:
    """Tests for _ensure_single_model() internals."""

    def test_skips_existing_file(self, tmp_path):
        model_info = {"filename": "test.pb", "url": "http://example.com/test.pb"}
        dest = tmp_path / "test.pb"
        dest.write_text("existing")

        with patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path):
            result = _ensure_single_model(model_info)

        assert result == dest
        assert dest.read_text() == "existing"

    def test_hash_verification_passes(self, tmp_path):
        content = b"model-content"
        import hashlib
        expected_hash = hashlib.sha256(content).hexdigest()

        model_info = {
            "filename": "test.pb",
            "url": "http://example.com/test.pb",
            "sha256": expected_hash,
        }

        def fake_urlretrieve(url, dest):
            Path(dest).write_bytes(content)

        with (
            patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path),
            patch(
                "vdj_manager.analysis.model_downloader.urllib.request.urlretrieve",
                side_effect=fake_urlretrieve,
            ),
        ):
            result = _ensure_single_model(model_info)

        assert result.exists()
        assert result.read_bytes() == content

    def test_hash_verification_fails(self, tmp_path):
        model_info = {
            "filename": "test.pb",
            "url": "http://example.com/test.pb",
            "sha256": "wrong_hash",
        }

        def fake_urlretrieve(url, dest):
            Path(dest).write_text("data")

        with (
            patch("vdj_manager.analysis.model_downloader.MODELS_DIR", tmp_path),
            patch(
                "vdj_manager.analysis.model_downloader.urllib.request.urlretrieve",
                side_effect=fake_urlretrieve,
            ),
        ):
            with pytest.raises(OSError, match="Hash mismatch"):
                _ensure_single_model(model_info)

        # No temp files or final files left
        assert not (tmp_path / "test.pb").exists()
        assert list(tmp_path.glob("*.tmp")) == []


class TestSha256:
    """Tests for _sha256 utility."""

    def test_correct_hash(self, tmp_path):
        import hashlib
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()

        f = tmp_path / "test.bin"
        f.write_bytes(content)

        assert _sha256(f) == expected

    def test_empty_file(self, tmp_path):
        import hashlib
        expected = hashlib.sha256(b"").hexdigest()

        f = tmp_path / "empty.bin"
        f.write_bytes(b"")

        assert _sha256(f) == expected
