"""The build stamp: which commit is actually running.

Deployment is pull-based, so nothing in the loop from a merge to a running
container reports what ended up deployed. These tests cover the three sources
the answer can come from and the one thing that must never happen -- a footer
confidently naming a commit it doesn't actually know.
"""

import unittest
from unittest.mock import patch

from oddsfantasy import build_info as build_info_module
from oddsfantasy.build_info import UNKNOWN, build_info
from tests.test_api import wsgi_get


class BuildInfoTest(unittest.TestCase):
    def setUp(self):
        # The real function is cached for the process lifetime; these tests
        # need it recomputed per case.
        build_info.cache_clear()
        self.addCleanup(build_info.cache_clear)

    def _env(self, **overrides):
        base = {
            "APP_COMMIT": "",
            "APP_BRANCH": "",
            "APP_IMAGE_TAG": "",
            "APP_BUILT_AT": "",
        }
        base.update(overrides)
        return patch.dict("os.environ", base, clear=False)

    def test_baked_env_wins(self):
        # What every deployed container uses: .dockerignore excludes .git, so
        # the env var is the only source available inside the image.
        with self._env(
            APP_COMMIT="a" * 40,
            APP_BRANCH="main",
            APP_IMAGE_TAG="latest",
            APP_BUILT_AT="2026-08-22T04:58:00Z",
        ):
            info = build_info()
        self.assertEqual(info["commit"], "a" * 40)
        self.assertEqual(info["commit_short"], "aaaaaaa")
        self.assertEqual(info["source"], "image")
        self.assertEqual(info["image_tag"], "latest")
        self.assertEqual(info["branch"], "main")
        self.assertEqual(info["built_at"], "2026-08-22T04:58:00Z")
        self.assertFalse(info["dirty"])

    def test_env_wins_over_git(self):
        with (
            self._env(APP_COMMIT="b" * 40),
            patch.object(build_info_module, "_from_git") as from_git,
        ):
            info = build_info()
        from_git.assert_not_called()
        self.assertEqual(info["commit"], "b" * 40)

    def test_placeholder_commit_is_treated_as_unset(self):
        # `docker build` with no build arg leaves the Dockerfile default.
        with (
            self._env(APP_COMMIT=UNKNOWN),
            patch.object(build_info_module, "_from_git", return_value=None),
        ):
            info = build_info()
        self.assertEqual(info["commit"], UNKNOWN)
        self.assertEqual(info["source"], UNKNOWN)

    def test_falls_back_to_git_in_a_checkout(self):
        with (
            self._env(),
            patch.object(
                build_info_module,
                "_from_git",
                return_value={
                    "commit": "c" * 40,
                    "dirty": True,
                    "source": "git",
                    "branch": "dev/thing",
                },
            ),
        ):
            info = build_info()
        self.assertEqual(info["source"], "git")
        self.assertEqual(info["commit_short"], "ccccccc")
        self.assertTrue(info["dirty"])

    def test_unknown_rather_than_a_wrong_answer(self):
        with self._env(), patch.object(build_info_module, "_from_git", return_value=None):
            info = build_info()
        self.assertEqual(info["commit"], UNKNOWN)
        self.assertEqual(info["commit_short"], UNKNOWN)
        self.assertIsNone(info["image_tag"])
        self.assertIsNone(info["branch"])

    def test_git_failure_never_raises(self):
        with self._env(), patch.object(build_info_module, "_git", return_value=None):
            info = build_info()
        self.assertIn(info["source"], ("git", UNKNOWN))
        self.assertEqual(info["commit"], UNKNOWN)

    def test_result_is_cached(self):
        with self._env(APP_COMMIT="d" * 40):
            first = build_info()
            second = build_info()
        self.assertIs(first, second)


class HealthExposesBuildTest(unittest.TestCase):
    def test_health_reports_the_running_commit(self):
        status, _headers, payload = wsgi_get("/health")
        self.assertTrue(status.startswith("200"))
        build = payload.get("build")
        self.assertIsInstance(build, dict)
        for key in ("commit", "commit_short", "source", "dirty", "image_tag", "branch", "built_at"):
            self.assertIn(key, build)


if __name__ == "__main__":
    unittest.main()
