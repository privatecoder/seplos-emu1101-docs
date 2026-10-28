"""Offline library identity, status and stale-input regressions."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('knowledge', HERE / 'knowledge.py')
knowledge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(knowledge)


class KnowledgeTests(unittest.TestCase):
    @staticmethod
    def valid_container():
        sys.path.insert(0, str(knowledge.PROJECT_ROOT/'mod/firmware/patcher'))
        try:
            from seplos.image import Image
            header_data = b'SWM181RCT6_64_M0EMU1101_10D_HW16RS485'.ljust(256, b' ')
            header = tuple(':10000000'+header_data[i:i+16].hex().upper()+'AA'
                           for i in range(0, 256, 16))
            app = struct.pack('<II', 0x20002000, 0xC1)+bytes(0x1000-8)
            return Image(header, app, (':04000005000000C136', ':00000001FF')).render()
        finally:
            sys.path.pop(0)

    def test_strict_parse_distinguishes_container_encoding_from_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'one.ehex'
            source.write_bytes(self.valid_container().encode('ascii'))
            first = knowledge.read_image(source)
            source.write_bytes(self.valid_container().replace('\n', '\r\n').encode('ascii'))
            second = knowledge.read_image(source)
            self.assertNotEqual(first['file_sha256'], second['file_sha256'])
            self.assertEqual(first['app_sha256'], second['app_sha256'])
            first['path'] = 'one.ehex'
            self.assertEqual(knowledge.match_image(second, [first])['identity'],
                             'known-application-different-container')

    def test_corrupt_body_is_refused_by_strict_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'bad.ehex'
            lines = self.valid_container().splitlines()
            lines[16] = lines[16][:-2]+'00'  # vector record checksum was nonzero
            source.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                knowledge.read_image(source)

    def test_same_application_different_container_is_known_not_exact(self):
        records = [{'path': 'vendor/firmware/a.ehex', 'file_sha256': 'a'*64,
                    'app_sha256': 'b'*64, 'roles': ['OEM']}]
        result = knowledge.match_image({'file_sha256': 'c'*64, 'app_sha256': 'b'*64}, records)
        self.assertEqual(result['identity'], 'known-application-different-container')
        self.assertEqual(result['matches'][0]['path'], records[0]['path'])

    def test_unknown_application_never_uses_filename_or_prefix(self):
        result = knowledge.match_image({'file_sha256': 'c'*64, 'app_sha256': 'b'*64},
                                       [{'path': 'same-name.ehex', 'file_sha256': 'c'*63+'0',
                                         'app_sha256': 'b'*63+'0'}])
        self.assertEqual(result['identity'], 'unknown-application')
        self.assertEqual(result['matches'], [])

    def test_failed_test_overrules_passed_report(self):
        self.assertEqual(knowledge.report_status({'status': 'passed', 'tests': [
            {'name': 'positive', 'passed': True}, {'name': 'fault', 'passed': False}]
        })['verdict'], 'recorded-failure')

    def test_patcher_test_failed_status_with_empty_tests_is_failure(self):
        self.assertEqual(knowledge.report_status({'status': 'test_failed', 'tests': [],
            'error': 'AssertionError: recovery counter'})['verdict'], 'recorded-failure')
        self.assertEqual(knowledge.report_status({'status': 'refused', 'error': 'unsupported ABI'})['verdict'],
                         'recorded-refusal')

    def test_refresh_does_not_rebaseline_a_changed_research_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'mod/tools').mkdir(parents=True)
            source = root/'fact.json'
            source.write_text('original facts')
            expected = knowledge.bind(root, source)
            (root/'mod/tools/research-inputs.json').write_text(json.dumps({'inputs': {'facts': expected}}))
            source.write_text('unexpected replacement')
            self.assertIn({'path': 'fact.json', 'problem': 'changed'}, knowledge.refresh(root)['errors'])

    def test_refresh_preserves_exact_artifact_source_container_and_extent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'vendor/firmware/source.ehex'
            source.parent.mkdir(parents=True)
            source.write_bytes(self.valid_container().encode('ascii'))
            identity = knowledge.read_image(source)
            artifact = root/'local/artifacts/firmware'/identity['app_sha256']/'binding.json'
            artifact.parent.mkdir(parents=True)
            binding = dict(source=source.relative_to(root).as_posix(),
                           container_sha256=identity['file_sha256'],
                           app_sha256=identity['app_sha256'], app_bytes=identity['app_bytes'])
            artifact.write_text(json.dumps(binding))
            self.assertEqual(knowledge.refresh(root)['errors'], [])
            source.write_bytes(self.valid_container().replace('\n', '\r\n').encode('ascii'))
            self.assertTrue(any(error['problem'] == 'artifact-source-binding-mismatch'
                                for error in knowledge.refresh(root)['errors']))
            source.write_bytes(self.valid_container().encode('ascii'))
            binding['app_bytes'] += 4
            artifact.write_text(json.dumps(binding))
            self.assertTrue(any(error['problem'] == 'artifact-source-binding-mismatch'
                                for error in knowledge.refresh(root)['errors']))

    def test_filename_and_unrelated_boolean_do_not_mean_pass(self):
        self.assertEqual(knowledge.report_status({'build': {'positive_flags': True}})['verdict'], 'unclassified')
        self.assertEqual(knowledge.report_status({'status': 'passed', 'tests': []})['verdict'], 'recorded-pass')

    def test_bindings_missing_and_stale_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'file.txt'
            source.write_text('first')
            binding = knowledge.bind(root, source)
            self.assertEqual(knowledge.check_bindings(root, [binding]), [])
            source.write_text('second')
            self.assertEqual(knowledge.check_bindings(root, [binding])[0]['problem'], 'changed')
            source.unlink()
            self.assertEqual(knowledge.check_bindings(root, [binding])[0]['problem'], 'missing')

    def test_binding_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(knowledge.check_bindings(Path(tmp), [{'path': '../secret',
                'sha256': 'a'*64, 'bytes': 1}])[0]['problem'], 'unsafe-path')

    def test_refresh_does_not_overwrite_curated_topic_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root/'local/index'
            index.mkdir(parents=True)
            (index/'topics.json').write_text(json.dumps({'curated_topics': [
                {'id': 'special', 'summary': 'A preserved manual conclusion.'}]}))
            knowledge.refresh(root)
            self.assertEqual(json.loads((index/'topics.json').read_text())['curated_topics'][0]['id'], 'special')

    def test_topic_query_has_no_parser_or_native_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root/'local/index'
            index.mkdir(parents=True)
            (index/'topics.json').write_text(json.dumps({'topics': [{'id': 'soc', 'summary': 'Counters'}],
                                                       'decisions': [], 'curated_topics': []}))
            original = knowledge.read_image
            knowledge.read_image = lambda *a: (_ for _ in ()).throw(AssertionError('unexpected parser'))
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(knowledge.main(['--project', str(root), 'topic', 'soc']), 0)
                self.assertIn('Counters', out.getvalue())
            finally:
                knowledge.read_image = original

    def test_refresh_known_metadata_requires_matching_application_and_container(self):
        self.assertEqual(knowledge.release_match({'file_sha256': 'a', 'app_sha256': 'b'},
            {'ehex_sha256': 'a', 'app_sha256': 'c'}), False)
        self.assertEqual(knowledge.release_match({'file_sha256': 'a', 'app_sha256': 'b'},
            {'ehex_sha256': 'a', 'app_sha256': 'b'}), True)


if __name__ == '__main__':
    unittest.main()
