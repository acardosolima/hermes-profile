"""Untrusted-input handling, failure exit codes, atomic swap and output modes."""

import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

try:
    from . import support
except ImportError:
    import support


def _can_symlink(tmp):
    probe = tmp / "probe-link"
    try:
        os.symlink(str(tmp), str(probe))
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


class UpstreamCopyCase(support.TempCase):
    def setUp(self):
        super().setUp()
        root, tag, sha = support.shared_upstream()
        self.upstream = support.copy_upstream(root, self.tmp / "u")
        self.lock = support.lock_for(self.upstream, tag, sha)

    def generate(self):
        return self.hs.generate(self.upstream, self.lock)


class ReadConfinementTests(UpstreamCopyCase):
    def test_symlink_in_references_is_rejected(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        secret = self.tmp / "outside.txt"
        secret.write_text("outside\n")
        link = self.upstream / "skills/harness-work/references/link.md"
        os.symlink(str(secret), str(link))
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_symlinked_references_directory_is_rejected(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        target = self.upstream / "skills/harness-plan/references"
        link = self.upstream / "skills/harness-work/references"
        if link.exists():
            support._rm(link)
        os.symlink(str(target), str(link))
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_symlinked_skill_file_is_rejected(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        skill = self.upstream / "skills/harness-work/SKILL.md"
        other = self.upstream / "skills/harness-plan/SKILL.md"
        skill.unlink()
        os.symlink(str(other), str(skill))
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_traversal_token_is_not_bundled(self):
        support.put(self.upstream, "secret.txt", "top secret\n")
        path = self.upstream / "skills/harness-work/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nSee scripts/a/../../secret.txt now.\n")
        files = self.generate()
        for key, data in files.items():
            with self.subTest(path=key):
                self.assertNotIn(b"top secret", data)
                self.assertNotIn("..", key.split("/"))

    def test_traversal_token_to_another_skill_file_is_not_bundled(self):
        path = self.upstream / "skills/harness-work/SKILL.md"
        path.write_bytes(
            path.read_bytes() + b"\nSee scripts/a/../../skills/harness-plan/SKILL.md now.\n"
        )
        files = self.generate()
        for key in files:
            with self.subTest(path=key):
                self.assertNotIn("..", key.split("/"))
                self.assertFalse(key.startswith("harness-work/scripts/a"))

    def test_script_symlink_to_outside_file_is_not_bundled(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        support.put(self.upstream, "secret.txt", "top secret\n")
        os.symlink(str(self.upstream / "secret.txt"), str(self.upstream / "scripts/leak.sh"))
        path = self.upstream / "skills/harness-work/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nRun scripts/leak.sh next.\n")
        for key, data in self.generate().items():
            with self.subTest(path=key):
                self.assertNotIn(b"top secret", data)

    def test_invalid_utf8_reference_raises_translate_error(self):
        support.put(self.upstream, "skills/harness-work/references/bad.md", b"\xff\xfe broken\n")
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_bom_in_markdown_reference_is_removed(self):
        support.put(self.upstream, "skills/harness-work/references/bom.md", b"\xef\xbb\xbf# Title\n")
        files = self.generate()
        self.assertEqual(files["harness-work/references/bom.md"], b"# Title\n")


class ByteExactnessTests(UpstreamCopyCase):
    def test_scripts_keep_crlf_and_non_ascii_bytes(self):
        body = "#!/bin/sh\r\necho caf\u00e9 \u2713\r\n".encode("utf-8")
        support.put(self.upstream, "scripts/crlf-utf8.sh", body)
        path = self.upstream / "skills/harness-work/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nRun scripts/crlf-utf8.sh next.\n")
        self.assertEqual(self.generate()["harness-work/scripts/crlf-utf8.sh"], body)

    def test_non_markdown_reference_is_copied_without_substitution(self):
        body = b'{"path": "${CLAUDE_SKILL_DIR}/x", "n": 1}\r\n\xff\xfe'
        support.put(self.upstream, "skills/harness-work/references/blob.bin", body)
        self.assertEqual(self.generate()["harness-work/references/blob.bin"], body)

    def test_nested_reference_directories_are_translated(self):
        support.put(
            self.upstream,
            "skills/harness-work/references/deep/er/note.md",
            "Use ${CLAUDE_SKILL_DIR}/references/x.md\r\n",
        )
        out = self.generate()["harness-work/references/deep/er/note.md"]
        self.assertEqual(out, b"Use references/x.md\n")


class OrderingTests(UpstreamCopyCase):
    TOKENS = ("ZED", "ALPHA", "MIKE", "BRAVO", "YANKEE", "CHARLIE")

    def test_manifest_lists_with_many_entries_are_sorted(self):
        extra = "".join(
            "\n${CLAUDE_%s} scripts/missing-%s.sh" % (t, t.lower()) for t in self.TOKENS
        )
        path = self.upstream / "skills/harness-work/SKILL.md"
        path.write_bytes(path.read_bytes() + extra.encode("utf-8") + b"\n")
        manifest = json.loads(self.generate()["GENERATED.json"].decode("utf-8"))
        entry = manifest["skills"]["harness-work"]
        for key in ("unresolved", "missing_scripts"):
            with self.subTest(key=key):
                self.assertGreaterEqual(len(entry[key]), len(self.TOKENS))
                self.assertEqual(entry[key], sorted(entry[key]))

    def test_missing_scripts_are_found_in_references_too(self):
        support.put(
            self.upstream,
            "skills/harness-work/references/more.md",
            "Run scripts/only-in-reference.sh first.\n",
        )
        manifest = json.loads(self.generate()["GENERATED.json"].decode("utf-8"))
        self.assertIn("scripts/only-in-reference.sh", manifest["skills"]["harness-work"]["missing_scripts"])


class HashSeedDeterminismTests(support.TempCase):
    def test_output_is_identical_across_hash_seeds(self):
        extra = "".join(
            "\n${CLAUDE_%s} scripts/missing-%s.sh" % (t, t.lower())
            for t in OrderingTests.TOKENS
        )
        base = support.fixture_files()["skills/harness-work/SKILL.md"]
        root, tag, sha = support.make_upstream(
            self.tmp / "x",
            overrides={"skills/harness-work/SKILL.md": base + extra.encode("utf-8") + b"\n"},
        )
        lock_path = self.tmp / "upstream.lock"
        support.write_lock(lock_path, support.lock_for(root, tag, sha))
        snapshots = []
        for seed in ("1", "2", "3"):
            out = self.tmp / ("out" + seed)
            env = support.isolated_env()
            env["PYTHONHASHSEED"] = seed
            proc = subprocess.run(
                [sys.executable, str(support.CLI_PATH), "sync", "--lock", str(lock_path),
                 "--out", str(out), "--source", str(root)],
                cwd=str(self.tmp), env=env, capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            snapshots.append(support.snapshot(out))
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0], snapshots[2])


class SecretScanScopeTests(support.TempCase):
    def test_plain_private_key_header_is_detected(self):
        with self.assertRaises(self.hs.SecretFoundError):
            self.hs.scan_secrets({"a/SKILL.md": b"-----BEGIN PRIVATE KEY-----\n"})

    def test_secrets_are_detected_in_scripts_and_json(self):
        secret = ("sk-ant-" + "a1b2c3d4e5f6").encode("utf-8")
        for path in ("skill/scripts/run.sh", "skill/references/data.json", "GENERATED.json"):
            with self.subTest(path=path):
                with self.assertRaises(self.hs.SecretFoundError) as ctx:
                    self.hs.scan_secrets({path: b"token=" + secret + b"\n"})
                self.assertIn(path, str(ctx.exception))
                self.assertNotIn(secret.decode("utf-8"), str(ctx.exception))


class WriteOutputParentsTests(support.TempCase):
    def test_multiple_missing_parent_levels_are_created(self):
        target = self.tmp / "a" / "b" / "c" / "out"
        self.hs.write_output({"x.txt": b"x\n"}, target)
        self.assertEqual((target / "x.txt").read_bytes(), b"x\n")


class FrontmatterOutputTests(UpstreamCopyCase):
    def test_description_with_colon_is_written_as_quoted_string(self):
        support.put(
            self.upstream,
            "skills/harness-work/SKILL.md",
            "---\nname: harness-work\ndescription: Review: diffs\n---\n# Body\n",
        )
        text = self.generate()["harness-work/SKILL.md"].decode("utf-8")
        self.assertIn('\ndescription: "Review: diffs"\n', text)
        self.assertIn('\nname: "harness-work"\n', text)

    def test_nested_indented_keys_do_not_override_top_level(self):
        data, _ = self.hs.split_frontmatter(
            "---\nname: top\nmetadata:\n  name: nested\n  description: nested desc\n---\nbody\n"
        )
        self.assertEqual(data["name"], "top")
        self.assertNotIn("description", data)


class LockStrictnessTests(support.TempCase):
    def test_sha_with_trailing_newline_is_rejected(self):
        path = self.tmp / "upstream.lock"
        support.write_lock(path, {"repo": "r", "tag": "t", "sha": "a" * 40 + "\n"})
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(path)


class FetchFailureTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.root, self.tag, self.sha = support.shared_upstream()
        self.lock = support.lock_for(self.root, self.tag, self.sha)

    def test_unknown_tag_raises_and_leaves_no_dest(self):
        dest = self.tmp / "dest"
        lock = dict(self.lock, tag="no-such-tag")
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(lock, dest)
        self.assertFalse(dest.exists())

    def test_unreachable_source_raises_and_leaves_no_dest(self):
        dest = self.tmp / "dest"
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(self.lock, dest, clone_url=str(self.tmp / "missing-repo"))
        self.assertFalse(dest.exists())

    def test_existing_dest_is_rejected_untouched(self):
        dest = self.tmp / "dest"
        dest.mkdir()
        (dest / "keep.txt").write_text("keep\n")
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(self.lock, dest)
        self.assertEqual((dest / "keep.txt").read_text(), "keep\n")

    def test_option_like_tag_is_rejected(self):
        dest = self.tmp / "dest"
        lock = dict(self.lock, tag="--upload-pack=evil")
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(lock, dest)
        self.assertFalse(dest.exists())

    def test_option_like_url_is_rejected(self):
        dest = self.tmp / "dest"
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(self.lock, dest, clone_url="--upload-pack=evil")
        self.assertFalse(dest.exists())


class WriteOutputSwapTests(support.TempCase):
    def test_failure_during_swap_restores_previous_contents(self):
        target = self.tmp / "out"
        self.hs.write_output({"a.txt": b"old\n"}, target)
        real_replace = os.replace
        calls = []

        def flaky(src, dst, *args, **kwargs):
            calls.append((str(src), str(dst)))
            if len(calls) == 2:
                raise OSError("simulated failure")
            return real_replace(src, dst, *args, **kwargs)

        with mock.patch.object(self.hs.os, "replace", side_effect=flaky):
            with self.assertRaises(OSError):
                self.hs.write_output({"a.txt": b"new\n"}, target)
        self.assertEqual((target / "a.txt").read_bytes(), b"old\n")
        leftovers = [p.name for p in self.tmp.iterdir() if p.name != "out"]
        self.assertEqual(leftovers, [])


@unittest.skipIf(os.name == "nt", "POSIX file modes only")
class OutputModeTests(support.TempCase):
    def test_shebang_scripts_are_executable_and_others_are_not(self):
        target = self.tmp / "out"
        self.hs.write_output(
            {
                "skill/scripts/run.sh": b"#!/usr/bin/env bash\necho hi\n",
                "skill/scripts/lib.sh": b"echo lib\n",
                "skill/SKILL.md": b"#!/not/a/script\n",
            },
            target,
        )
        self.assertTrue(os.access(str(target / "skill/scripts/run.sh"), os.X_OK))
        self.assertFalse(os.access(str(target / "skill/scripts/lib.sh"), os.X_OK))
        self.assertFalse(os.access(str(target / "skill/SKILL.md"), os.X_OK))

    def test_output_directories_are_world_readable(self):
        target = self.tmp / "out"
        self.hs.write_output({"skill/SKILL.md": b"x\n"}, target)
        for path in (target, target / "skill"):
            with self.subTest(path=path.name):
                self.assertEqual(path.stat().st_mode & 0o755, 0o755)


class CliFailureTests(support.TempCase):
    def run_sync(self, overrides):
        root, tag, sha = support.make_upstream(self.tmp / "x", overrides=overrides)
        lock_path = self.tmp / "upstream.lock"
        support.write_lock(lock_path, support.lock_for(root, tag, sha))
        out = self.tmp / "out"
        support.put(out, "keep.txt", "previous\n")
        proc = subprocess.run(
            [sys.executable, str(support.CLI_PATH), "sync", "--lock", str(lock_path),
             "--out", str(out), "--source", str(root)],
            cwd=str(self.tmp),
            env=support.isolated_env(),
            capture_output=True,
        )
        return proc, out

    def test_translate_error_exits_two_and_keeps_previous_output(self):
        proc, out = self.run_sync(
            {"skills/harness-plan/SKILL.md": "---\nname: harness-plan\n---\n# no description\n"}
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual((out / "keep.txt").read_text(), "previous\n")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["keep.txt"])

    def test_invalid_utf8_reference_exits_two(self):
        proc, out = self.run_sync({"skills/harness-plan/references/bad.md": b"\xff\xfe\n"})
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual((out / "keep.txt").read_text(), "previous\n")

    def test_unwritable_output_parent_exits_two(self):
        root, tag, sha = support.shared_upstream()
        lock_path = self.tmp / "upstream.lock"
        support.write_lock(lock_path, support.lock_for(root, tag, sha))
        blocker = self.tmp / "blocker"
        blocker.write_text("a file, not a directory\n")
        proc = subprocess.run(
            [sys.executable, str(support.CLI_PATH), "sync", "--lock", str(lock_path),
             "--out", str(blocker / "out"), "--source", str(root)],
            cwd=str(self.tmp),
            env=support.isolated_env(),
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn(b"Traceback", proc.stderr)


class RoundTwoConfinementTests(UpstreamCopyCase):
    def append(self, rel, text):
        path = self.upstream / rel
        path.write_bytes(path.read_bytes() + text.encode("utf-8"))

    def manifest(self, files):
        return json.loads(files["GENERATED.json"].decode("utf-8"))

    def test_symlinked_skill_directory_is_rejected(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        skill = self.upstream / "skills/harness-work"
        support._rm(skill)
        os.symlink(str(self.upstream / "skills/harness-plan"), str(skill))
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_symlink_to_file_inside_same_skill_is_rejected(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        refs = self.upstream / "skills/harness-work/references"
        os.symlink(str(refs / "work-detail.md"), str(refs / "alias.md"))
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_dot_dot_token_resolving_to_a_real_script_is_not_bundled(self):
        self.append("skills/harness-work/SKILL.md", "\nRun scripts/sub/../plan-check.sh next.\n")
        files = self.generate()
        self.assertFalse([key for key in files if ".." in key.split("/")])
        missing = self.manifest(files)["skills"]["harness-work"]["missing_scripts"]
        self.assertIn("scripts/sub/../plan-check.sh", missing)

    def test_non_canonical_token_is_reported_not_bundled(self):
        support.put(self.upstream, "scripts/a/b.sh", "echo b\n")
        self.append("skills/harness-work/SKILL.md", "\nRun scripts/a//b.sh next.\n")
        files = self.generate()
        self.assertFalse([key for key in files if "//" in key])
        self.assertNotIn("harness-work/scripts/a/b.sh", files)
        missing = self.manifest(files)["skills"]["harness-work"]["missing_scripts"]
        self.assertIn("scripts/a//b.sh", missing)

    def test_invalid_utf8_skill_file_raises_translate_error(self):
        support.put(self.upstream, "skills/harness-work/SKILL.md", b"---\nname: x\n---\n\xff\xfe\n")
        with self.assertRaises(self.hs.TranslateError):
            self.generate()

    def test_git_directory_inside_references_is_skipped(self):
        support.put(
            self.upstream, "skills/harness-work/references/.git/config", "url = https://token@host/x\n"
        )
        files = self.generate()
        self.assertFalse([key for key in files if ".git" in key.split("/")])

    def test_missing_tokens_in_scripts_and_json_are_not_reported(self):
        support.put(self.upstream, "scripts/has-ghost.sh", "echo scripts/ghost-in-script.sh\n")
        support.put(self.upstream, "skills/harness-work/references/info.json", '{"x": "scripts/ghost-in-json.sh"}')
        self.append("skills/harness-work/SKILL.md", "\nRun scripts/has-ghost.sh next.\n")
        files = self.generate()
        self.assertIn("harness-work/scripts/has-ghost.sh", files)
        missing = self.manifest(files)["skills"]["harness-work"]["missing_scripts"]
        self.assertNotIn("scripts/ghost-in-script.sh", missing)
        self.assertNotIn("scripts/ghost-in-json.sh", missing)


class UnexpectedErrorTests(support.TempCase):
    def run_main_with(self, **patches):
        root, tag, sha = support.shared_upstream()
        lock_path = self.tmp / "upstream.lock"
        support.write_lock(lock_path, support.lock_for(root, tag, sha))
        stderr = io.StringIO()
        with mock.patch.multiple(self.hs, **patches), mock.patch.object(sys, "stderr", stderr):
            code = self.hs.main(
                ["check", "--lock", str(lock_path), "--out", str(self.tmp / "out"), "--source", str(root)]
            )
        return code, stderr.getvalue()

    def test_unexpected_value_error_exits_two_with_type_name(self):
        code, err = self.run_main_with(fetch_upstream=mock.Mock(side_effect=ValueError("boom")))
        self.assertEqual(code, 2)
        self.assertIn("ValueError: boom", err)
        self.assertNotIn("Traceback", err)

    def test_unexpected_key_error_keeps_its_type_in_the_message(self):
        code, err = self.run_main_with(generate=mock.Mock(side_effect=KeyError("sha")))
        self.assertEqual(code, 2)
        self.assertIn("KeyError", err)


class GitArgumentTests(support.TempCase):
    def test_nul_in_url_or_tag_raises_fetch_error(self):
        root, tag, sha = support.shared_upstream()
        lock = support.lock_for(root, tag, sha)
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(lock, self.tmp / "d1", clone_url="a\x00b")
        with self.assertRaises(self.hs.FetchError):
            self.hs.fetch_upstream(dict(lock, tag="v\x00"), self.tmp / "d2")
        self.assertFalse((self.tmp / "d1").exists() or (self.tmp / "d2").exists())

    def test_symlinked_skills_directory_is_rejected(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        root, tag, sha = support.shared_upstream()
        copy = support.copy_upstream(root, self.tmp / "u")
        real = copy / "skills-real"
        os.rename(str(copy / "skills"), str(real))
        os.symlink(str(real), str(copy / "skills"))
        with self.assertRaises(self.hs.TranslateError):
            self.hs.generate(copy, support.lock_for(copy, tag, sha))

    def test_script_symlink_alias_is_reported_missing_not_bundled(self):
        if not _can_symlink(self.tmp):
            self.skipTest("symlinks unavailable")
        root, tag, sha = support.shared_upstream()
        copy = support.copy_upstream(root, self.tmp / "u")
        os.symlink(str(copy / "scripts/plan-check.sh"), str(copy / "scripts/alias.sh"))
        path = copy / "skills/harness-work/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nRun scripts/alias.sh next.\n")
        files = self.hs.generate(copy, support.lock_for(copy, tag, sha))
        self.assertNotIn("harness-work/scripts/alias.sh", files)
        manifest = json.loads(files["GENERATED.json"].decode("utf-8"))
        self.assertIn("scripts/alias.sh", manifest["skills"]["harness-work"]["missing_scripts"])


class PreambleMarkerTests(UpstreamCopyCase):
    def test_degraded_and_unverified_mappings_are_marked(self):
        text = self.generate()["harness-work/SKILL.md"].decode("utf-8")
        self.assertIn("delegate_task (degraded)", text)
        self.assertIn("cronjob (degraded)", text)
        self.assertIn("patch arguments unverified", text)


class RoundTwoSecretTests(support.TempCase):
    def test_secret_in_file_with_invalid_utf8_is_detected(self):
        data = b"\xff\xfe token=" + ("sk-ant-" + "a1b2c3d4e5f6").encode("utf-8") + b"\n"
        with self.assertRaises(self.hs.SecretFoundError):
            self.hs.scan_secrets({"skill/scripts/odd.sh": data})


class RoundTwoLockTests(support.TempCase):
    def lock(self, **overrides):
        data = {"repo": "r", "tag": "t", "sha": "a" * 40}
        data.update(overrides)
        path = self.tmp / "upstream.lock"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_nul_in_tag_is_rejected(self):
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(self.lock(tag="v1\u0000"))

    def test_non_string_repo_is_rejected(self):
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(self.lock(repo=5))

    def test_invalid_utf8_lock_raises_lock_error(self):
        path = self.tmp / "upstream.lock"
        path.write_bytes(b'{"repo": "\xff"}')
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(path)

    def test_huge_integer_lock_raises_lock_error(self):
        path = self.tmp / "upstream.lock"
        path.write_text('{"repo": "r", "tag": "t", "sha": 1' + "0" * 6000 + "}", encoding="utf-8")
        with self.assertRaises(self.hs.LockError):
            self.hs.load_lock(path)

    def test_cli_exits_two_without_traceback_for_bad_locks(self):
        for label, data in (
            ("nul tag", json.dumps({"repo": "r", "tag": "v\u0000", "sha": "a" * 40}).encode()),
            ("invalid utf-8", b'{"repo": "\xff"}'),
        ):
            with self.subTest(label):
                path = self.tmp / "bad.lock"
                path.write_bytes(data)
                proc = subprocess.run(
                    [sys.executable, str(support.CLI_PATH), "check", "--lock", str(path),
                     "--out", str(self.tmp / "out"), "--source", str(self.tmp)],
                    cwd=str(self.tmp), env=support.isolated_env(), capture_output=True,
                )
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertNotIn(b"Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
