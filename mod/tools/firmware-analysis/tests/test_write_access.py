"""Current catalogue identity, semantic equality and historical independence."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE.parents[2]
PUBLIC = ('ext-light.json', 'ext-full.json')


class CatalogueTests(unittest.TestCase):
    def command(self, source, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(source), *args],
                              capture_output=True, text=True, cwd='/private/tmp')

    def isolated_project(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        analysis = root / 'mod/tools/firmware-analysis'
        shutil.copytree(HERE, analysis, ignore=shutil.ignore_patterns('tests', '__pycache__', 'emulators', 'write_access_revision*', 'write_access_v16.py'))
        shutil.copy2(HERE.parent / '_paths.py', analysis.parent / '_paths.py')
        for name in PUBLIC:
            original = PROJECT / 'mod/firmware/releases' / name
            target = root / 'mod/firmware/releases' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            metadata = json.loads(original.read_text())
            image = root / 'local/releases' / metadata['name']
            image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / 'local/releases' / metadata['name'], image)
        vendor = root / 'vendor/firmware'
        vendor.mkdir(parents=True)
        shutil.copy2(PROJECT / 'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex', vendor)
        package = root / 'mod/firmware/patcher/seplos'
        package.mkdir(parents=True)
        for name in ('__init__.py', 'image.py'):
            shutil.copy2(PROJECT / 'mod/firmware/patcher/seplos' / name, package)
        return root, analysis / 'write_access.py'

    def synthetic_project(self):
        """Real container codec and fake releases; no executable/native evidence."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        analysis = root / 'mod/tools/firmware-analysis'
        analysis.mkdir(parents=True)
        for name in ('write_access.py', 'write_access_data.json', 'write_access.template.md'):
            shutil.copy2(HERE / name, analysis / name)
        shutil.copy2(HERE.parent / '_paths.py', analysis.parent / '_paths.py')
        package = root / 'mod/firmware/patcher/seplos'
        package.mkdir(parents=True)
        for name in ('__init__.py', 'image.py'):
            shutil.copy2(PROJECT / 'mod/firmware/patcher/seplos' / name, package)
        spec = importlib.util.spec_from_file_location('catalogue_image', package / 'image.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        vendor = root / 'vendor/firmware'
        vendor.mkdir(parents=True)
        original = PROJECT / 'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex'
        shutil.copy2(original, vendor)
        base = module.Image.read(original)
        manifests = root / 'mod/firmware/releases'
        manifests.mkdir(parents=True)
        images = root / 'local/releases'
        images.mkdir(parents=True)
        for version, flags, name in (('1.5.6', 0x3a, PUBLIC[0]), ('1.6.7', 0xfe, PUBLIC[1])):
            app = bytearray(base.app[:0x1000])
            app[4:8] = (0xc1).to_bytes(4, 'little')
            info = b'EXT\5\x10\6\x0d' + bytes(map(int, version.split('.'))) + b'UPID0000' + bytes([flags]) + (31 if version=='1.6.7' else 15).to_bytes(2,'big')
            template = info[:4] + bytes(2) + info[6:]
            app[0x200:0x200+len(template)] = template
            build_id = hashlib.sha256(app).digest()[:8]
            app[0x20a:0x212] = build_id
            image = base.with_app(app)
            rendered = image.render().encode()
            image_name = version + '-synthetic.ehex'
            (images / image_name).write_bytes(rendered)
            metadata = dict(patch_version=version, name=image_name, info_format=5, info_bytes=21,
                            remote_capabilities=31 if version=='1.6.7' else 15, image_flags=flags, build_id=build_id.hex(),
                            info_hex=(info[:10]+build_id+info[18:]).hex(), app_bytes=len(app),
                            app_sha256=image.sha, ehex_sha256=hashlib.sha256(rendered).hexdigest(),
                            extended_diagnostics=True, checkpoint_before_reset=flags==0xfe,
                            configurable_hard_stop=flags==0xfe, hard_stop_default=False)
            (manifests / name).write_text(json.dumps(metadata))
        return root, analysis / 'write_access.py'

    def test_catalogue_preserves_permissions_dimensions_and_adds_explicit_reads(self):
        root, source = self.synthetic_project()
        result = self.command(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(set(data['profiles']), {'1.5.6', '1.6.7'})
        self.assertEqual((len(data['parameters']), len(data['function_bits']), len(data['matrix'])), (87, 64, 24))
        self.assertEqual([p['index'] for p in data['parameters']], list(range(87)))
        self.assertEqual({(p['group'], p['bit']) for p in data['function_bits']},
                         {(group, bit) for group in range(8) for bit in range(8)})
        for version, profile in data['profiles'].items():
            self.assertEqual(profile['remote_capabilities'], 31 if version=='1.6.7' else 15)
            self.assertEqual(profile['info_format'], 5)
            self.assertEqual(profile['power_rtc_enabled_bit3'], 1)
            self.assertEqual(profile['manifest'], 'mod/firmware/releases/' +
                             ('ext-light.json' if version=='1.5.6' else 'ext-full.json'))
        self.assertIsNone(data['profiles']['1.5.6']['extended_off_enabled_bit4'])
        self.assertIsNone(data['profiles']['1.5.6']['lock_status_bit5'])
        self.assertEqual(data['profiles']['1.6.7']['extended_off_enabled_bit4'], 1)
        self.assertEqual(data['profiles']['1.6.7']['lock_status_bit5'], 0)
        rows = data['selected_read_commands']
        for label, command in (('Read one history record', '4B'),
                               ('Read active/stored calibration', '64/05'),
                               ('Read persisted capacity/SOC contents', '64/06'),
                               ('Read full-width live charged/discharged energy', '64/06')):
            row = next(row for row in rows if row[0] == label)
            self.assertIn(command, row[1])
            for cell in row[3:5]:
                self.assertIn('R', cell)
                self.assertIn('C', cell)
                self.assertIn('no permission', cell)
                self.assertNotIn('[W]', cell)
                self.assertNotIn('[P]', cell)
            self.assertEqual(row[2], 'R' if command=='4B' else '—')
        actions = {row[0]: row for row in data['matrix']}
        self.assertEqual(actions['Clear history, cycles and charge/discharge energy'][2:], ['R']*3)
        self.assertEqual(actions['Calibrate current zero'][2:], ['R']*3)
        self.assertEqual(actions['Calibrate current gain'][2:], ['R']*3)
        reset = actions['Local restart']
        self.assertNotIn('checkpoint', reset[3].lower())
        self.assertIn('SOC checkpoint', reset[4])

    def test_synthetic_EXT05_verifies_caps_flags_and_neutral_build_id(self):
        root, source = self.synthetic_project()
        result = self.command(source, '--verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['passed'])
        self.assertFalse(report['hardware_access'])
        self.assertEqual(set(report['profiles']), {'1.5.6', '1.6.7'})
        for version, profile in report['profiles'].items():
            self.assertEqual(profile['remote_capabilities'], 31 if version=='1.6.7' else 15)
            info = bytes.fromhex(profile['info_hex'])
            self.assertEqual(len(info), 21)
            self.assertEqual(info[18], 0x3a if version=='1.5.6' else 0xfe)
            self.assertEqual(info[19:], (31 if version=='1.6.7' else 15).to_bytes(2,'big'))

    def test_synthetic_renderer_labels_only_current_profiles_and_canonical_ports(self):
        root, source = self.synthetic_project()
        result = self.command(source, '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout
        self.assertIn('EMU1101-EXT Light 1.5.6', text)
        self.assertIn('EMU1101-EXT Full 1.6.7', text)
        self.assertIn('EXT05 image flags', text)
        self.assertIn('capability mask u16 BE 000F', text)
        self.assertIn('| Read one history record |', text)
        self.assertIn('| Read active/stored calibration |', text)
        self.assertIn('| Read persisted capacity/SOC contents |', text)
        self.assertIn('| Read full-width live charged/discharged energy |', text)
        self.assertIn('| UART0, UART1[W], UART2 |', text)
        self.assertNotRegex(text, r'\b[RCD](?:/[RCD])+\b')
        self.assertIn('Light 1.5.3', text)
        self.assertIn('Full 1.6.3', text)
        self.assertIn('Light 1.5.4', text)
        self.assertIn('Full 1.6.4', text)
        self.assertIn('EXT05 patch bytes are 01 05 06 / 01 06 07', text)
        self.assertNotIn('@PROFILES@', text)

    def test_new_interfaces_are_bold_relative_to_available_OEM_routes(self):
        root, source = self.synthetic_project()
        result = self.command(source, '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        def row(label):
            line = next(line for line in result.stdout.splitlines() if line.startswith('| '+label+' |'))
            return [cell.strip() for cell in line.strip('|').split('|')]
        self.assertEqual(row('All 87 configuration parameters P0–P86')[2:],
                         ['UART0, UART2', 'UART0, **UART1**[W], UART2', 'UART0, **UART1**[W], UART2'])
        self.assertEqual(row('Read parameters, switches and device name')[3:],
                         ['UART0: ASCII; **UART1**/UART2: binary']*2)
        self.assertEqual(row('Read firmware identity / version / build / image flags')[3:],
                         ['**UART0**, **UART1**: each addressed pack; UART2: —']*2)
        self.assertEqual(row('Read one history record')[3:],
                         ['UART0, **UART1**; no permission required']*2)
        self.assertEqual(row('Configure hard stop during recharge waiting')[3:],
                         ['—', '**UART0**, **UART1**[W], **UART2**; write together'])
        self.assertEqual(row('Calibrate current zero')[2:], ['UART0']*3)
        self.assertEqual(row('Group0.Bit0')[2:4], ['1 = allow writes over **UART1**']*2)
        self.assertEqual(row('Group0.Bit3')[2:4], ['**1 = allow Power/RTC over UART1**, 0 = blocked']*2)

    def test_EXT05_rejects_missing_unknown_or_mismatched_capabilities(self):
        root, source = self.synthetic_project()
        path = root / 'mod/firmware/releases' / PUBLIC[0]
        original = json.loads(path.read_text())
        mutations = []
        missing = dict(original)
        del missing['remote_capabilities']
        mutations.append(missing)
        for mask in (0, 1, 0x100, 0x800f, True, '15'):
            bad = dict(original, remote_capabilities=mask)
            mutations.append(bad)
        mutations.append(dict(original, info_format=4))
        mutations.append(dict(original, info_bytes=19))
        mutations.append(dict(original, info_hex=original['info_hex'][:-2]))
        mutations.append(dict(original, info_hex=original['info_hex'][:-4]+'0f00'))
        for metadata in mutations:
            path.write_text(json.dumps(metadata))
            result = self.command(source, '--verify')
            self.assertNotEqual(result.returncode, 0, metadata)
            self.assertIn('EXT05', result.stderr)

    def test_current_verify_needs_no_historical_modules_or_build_reports(self):
        root, source = self.isolated_project()
        self.assertFalse((root / 'local/builds').exists())
        result = self.command(source, '--verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['passed'])
        self.assertEqual(report['verification'], 'current release hashes and EXT05 metadata; no native emulation')
        self.assertEqual(set(report['profiles']), {'1.5.6', '1.6.7'})
        result = self.command(source, '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('All 87 A1 parameters', result.stdout)

    def test_current_catalogue_rejects_previous_release_metadata(self):
        root, source = self.synthetic_project()
        path = root / 'mod/firmware/releases' / PUBLIC[0]
        metadata = json.loads(path.read_text())
        metadata['patch_version'] = '1.5.4'
        path.write_text(json.dumps(metadata))
        for options in ((), ('--markdown',), ('--verify',)):
            with self.subTest(options=options):
                result = self.command(source, *options)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('release version mismatch', result.stderr)

    def test_current_verify_rejects_mismatched_public_metadata(self):
        root, source = self.isolated_project()
        path = root / 'mod/firmware/releases' / PUBLIC[0]
        data = json.loads(path.read_text())
        data['build_id'] = '0000000000000000'
        path.write_text(json.dumps(data))
        result = self.command(source, '--verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('EXT05', result.stderr)

    def test_published_catalogue_has_no_frozen_historical_model(self):
        for name in ('historical_write_model.py', 'historical_write_model.json',
                     'write_access_provenance.json', 'probe_write_access.py'):
            self.assertFalse((HERE / name).exists(), name)
        source = (HERE / 'write_access.py').read_text()
        self.assertNotIn('historical_write_model', source)


    def test_published_matrix_matches_current_renderer(self):
        result = self.command(HERE / 'write_access.py', '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        published = (PROJECT / 'mod/docs/firmware/uart-write-capabilities.md').read_text()
        self.assertTrue(result.stdout == published,
                        'Published capabilities must equal write_access.py --markdown; regenerate from the current template.')

    def test_markdown_displays_canonical_ports_without_changing_raw_catalogue(self):
        result = self.command(HERE / 'write_access.py', '--markdown')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| UART0, UART1[W], UART2 |', result.stdout)
        self.assertNotRegex(result.stdout, r'\b[RCD](?:/[RCD])+\b')
        raw = self.command(HERE / 'write_access.py')
        data = json.loads(raw.stdout)
        self.assertIn('R', json.dumps(data['matrix']))

    def test_output_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'existing.json'
            output.write_text('retain me')
            result = self.command(HERE / 'write_access.py', '--out', str(output))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), 'retain me')


if __name__ == '__main__':
    unittest.main()
