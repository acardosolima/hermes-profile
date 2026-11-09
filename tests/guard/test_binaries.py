"""Platform detection, download verification and the committed lock."""

import hashlib
import unittest

import support

binaries = support.binaries


def lock_with(content=b"binary-bytes", key="linux-amd64"):
    return {
        "repo": "https://github.com/example-owner/example-repo.git",
        "sha": "a" * 40,
        "tag": "v1.0.0",
        "binaries": {key: {"file": f"bin/harness-{key}", "sha256": hashlib.sha256(content).hexdigest()}},
    }


class PlatformKeyTests(unittest.TestCase):
    def test_supported_combinations(self):
        cases = {
            ("linux", "x86_64"): "linux-amd64",
            ("linux", "aarch64"): "linux-arm64",
            ("darwin", "arm64"): "darwin-arm64",
            ("darwin", "x86_64"): "darwin-amd64",
            ("win32", "AMD64"): "windows-amd64",
        }
        for (system, machine), expected in cases.items():
            with self.subTest(system=system, machine=machine):
                self.assertEqual(binaries.platform_key(system, machine), expected)

    def test_unsupported_values_raise(self):
        for system, machine in (("freebsd", "x86_64"), ("linux", "riscv64")):
            with self.subTest(system=system, machine=machine):
                with self.assertRaises(binaries.BinaryError):
                    binaries.platform_key(system, machine)


class DownloadUrlTests(unittest.TestCase):
    def test_url_pins_the_commit(self):
        url = binaries.download_url(lock_with(), "bin/harness-linux-amd64")
        self.assertEqual(
            url,
            "https://raw.githubusercontent.com/example-owner/example-repo/" + "a" * 40 + "/bin/harness-linux-amd64",
        )

    def test_rejects_other_hosts_bad_shas_and_traversal(self):
        good = lock_with()
        for label, lock, rel in (
            ("other host", dict(good, repo="https://evil.example/x/y.git"), "bin/x"),
            ("short sha", dict(good, sha="abc"), "bin/x"),
            ("traversal", good, "bin/../../x"),
        ):
            with self.subTest(label):
                with self.assertRaises(binaries.BinaryError):
                    binaries.download_url(lock, rel)


class EnsureBinaryTests(support.TempCase):
    def fetcher(self, content, calls):
        def fetch(url, destination):
            calls.append(url)
            destination.write_bytes(content)

        return fetch

    def test_downloads_verifies_and_caches(self):
        calls = []
        lock = lock_with()
        path = binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetcher(b"binary-bytes", calls))
        self.assertEqual(path.read_bytes(), b"binary-bytes")
        again = binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetcher(b"binary-bytes", calls))
        self.assertEqual(again, path)
        self.assertEqual(len(calls), 1)

    def test_hash_mismatch_raises_and_leaves_nothing(self):
        with self.assertRaises(binaries.BinaryError):
            binaries.ensure_binary(lock_with(), self.tmp, "linux-amd64", fetch=self.fetcher(b"tampered", []))
        leftovers = [p for p in self.tmp.rglob("*") if p.is_file()]
        self.assertEqual(leftovers, [])

    def test_corrupted_cache_is_replaced(self):
        calls = []
        lock = lock_with()
        path = binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetcher(b"binary-bytes", calls))
        path.write_bytes(b"corrupted")
        binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetcher(b"binary-bytes", calls))
        self.assertEqual(path.read_bytes(), b"binary-bytes")
        self.assertEqual(len(calls), 2)

    def test_download_failure_becomes_binary_error(self):
        def fetch(url, destination):
            raise OSError("offline")

        with self.assertRaises(binaries.BinaryError):
            binaries.ensure_binary(lock_with(), self.tmp, "linux-amd64", fetch=fetch)

    def test_platform_without_a_pinned_binary_raises(self):
        with self.assertRaises(binaries.BinaryError):
            binaries.ensure_binary(lock_with(), self.tmp, "linux-arm64", fetch=self.fetcher(b"x", []))


class FakeResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, size=-1):
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DownloadTests(support.TempCase):
    def test_streamed_download_is_written_in_full(self):
        from unittest import mock

        target = self.tmp / "out.bin"
        with mock.patch.object(binaries.urllib.request, "urlopen", return_value=FakeResponse([b"ab", b"cd"])):
            binaries._fetch("https://example.invalid/x", target)
        self.assertEqual(target.read_bytes(), b"abcd")

    def test_size_cap_stops_an_oversized_download(self):
        from unittest import mock

        target = self.tmp / "out.bin"
        with mock.patch.object(binaries, "MAX_BINARY_BYTES", 3):
            with mock.patch.object(binaries.urllib.request, "urlopen", return_value=FakeResponse([b"ab", b"cd"])):
                with self.assertRaises(binaries.BinaryError):
                    binaries._fetch("https://example.invalid/x", target)

    def test_oversized_download_leaves_no_cached_binary(self):
        from unittest import mock

        with mock.patch.object(binaries, "MAX_BINARY_BYTES", 3):
            with mock.patch.object(binaries.urllib.request, "urlopen", return_value=FakeResponse([b"ab", b"cd"])):
                with self.assertRaises(binaries.BinaryError):
                    binaries.ensure_binary(lock_with(b"abcd"), self.tmp, "linux-amd64")
        self.assertEqual([p for p in self.tmp.rglob("*") if p.is_file()], [])


class TamperAndCacheTests(support.TempCase):
    def fetch(self, content):
        def fetch(url, destination):
            destination.write_bytes(content)

        return fetch

    def test_a_binary_replaced_after_download_is_not_returned(self):
        lock = lock_with()
        path = binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetch(b"binary-bytes"))
        path.write_bytes(b"evil replacement")
        again = binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetch(b"binary-bytes"))
        self.assertEqual(again.read_bytes(), b"binary-bytes")

    def test_replacement_with_a_failing_download_raises_instead_of_returning_the_bad_file(self):
        lock = lock_with()
        path = binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=self.fetch(b"binary-bytes"))
        path.write_bytes(b"evil replacement")

        def offline(url, destination):
            raise OSError("offline")

        with self.assertRaises(binaries.BinaryError):
            binaries.ensure_binary(lock, self.tmp, "linux-amd64", fetch=offline)

    def test_an_unusable_cache_directory_is_a_binary_error(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("a file where a directory is needed\n", encoding="utf-8")
        with self.assertRaises(binaries.BinaryError):
            binaries.ensure_binary(lock_with(), blocker / "cache", "linux-amd64", fetch=self.fetch(b"binary-bytes"))

    def test_dot_owner_or_repo_is_rejected(self):
        for repo in ("https://github.com/../x.git", "https://github.com/x/...git"):
            with self.subTest(repo=repo):
                with self.assertRaises(binaries.BinaryError):
                    binaries.download_url(dict(lock_with(), repo=repo), "bin/harness-linux-amd64")


class CommittedLockTests(unittest.TestCase):
    def test_lock_describes_every_supported_platform(self):
        lock = support.real_lock()
        for key in ("linux-amd64", "darwin-amd64", "darwin-arm64", "windows-amd64"):
            with self.subTest(key=key):
                entry = lock["binaries"][key]
                self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(entry["file"].startswith("bin/harness-"))

    def test_lock_pins_the_same_release_as_upstream_lock(self):
        import json

        upstream = json.loads((support.ROOT / "upstream.lock").read_text(encoding="utf-8"))
        lock = support.real_lock()
        self.assertEqual((lock["tag"], lock["sha"]), (upstream["tag"], upstream["sha"]))


if __name__ == "__main__":
    unittest.main()
