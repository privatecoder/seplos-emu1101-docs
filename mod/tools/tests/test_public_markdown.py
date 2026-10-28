"""Public-checkout link eligibility must not depend on ignored local files."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
TOOL=HERE.parent/'check_markdown.py'

class PublicMarkdown(unittest.TestCase):
 def module(self):
  self.assertTrue(TOOL.is_file(),'public Markdown checker missing')
  spec=importlib.util.spec_from_file_location('public_markdown',TOOL);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def repo(self,path):
  subprocess.run(['git','init','-q',str(path)],check=True,capture_output=True)
 def write(self,root,name,text):
  f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text);return f
 def test_ignored_target_is_rejected_even_when_present(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'.gitignore','/local/\n');self.write(root,'README.md','# Project\n\n[Evidence](local/proof.md)\n');self.write(root,'local/proof.md','# Proof\n')
   report=m.check(root)
   self.assertFalse(report['passed']);self.assertEqual(report['issues'][0]['kind'],'unpublished_target')
 def test_new_public_files_are_candidates_but_index_only_requires_staging(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'README.md','# Project\n\n[License](LICENSE)\n');self.write(root,'LICENSE','Terms\n');subprocess.run(['git','add','README.md'],cwd=root,check=True)
   self.assertTrue(m.check(root)['passed'])
   self.assertFalse(m.check(root,index_only=True)['passed'])
   subprocess.run(['git','add','LICENSE'],cwd=root,check=True);self.assertTrue(m.check(root,index_only=True)['passed'])
 def test_directory_percent_encoded_filename_and_duplicate_anchor(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'README.md','# Project\n\n[Docs](docs/)\n[Part](docs/a%20b.md#part-1)\n');self.write(root,'docs/a b.md','# Guide\n\n## Part\n\n## Part\n')
   self.assertTrue(m.check(root)['passed'])
 def test_missing_targets_and_anchors_are_errors_but_fenced_samples_are_ignored(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'README.md','# Project\n\n[Missing](none.md)\n[Anchor](README.md#absent)\n```md\n[Example](ignored.md)\n```\n')
   kinds=[i['kind'] for i in m.check(root)['issues']];self.assertEqual(kinds,['unpublished_target','missing_anchor'])

 def test_subdirectory_is_not_mistaken_for_an_empty_valid_project(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'docs/README.md','# Guide\n')
   with self.assertRaisesRegex(ValueError,'repository root'):
    m.check(root/'docs')

 def test_public_symlink_cannot_borrow_an_ignored_private_target(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'.gitignore','/local/\n');self.write(root,'README.md','# Project\n\n[Evidence](docs/evidence.md)\n');self.write(root,'local/proof.md','# Private proof\n');(root/'docs').mkdir();(root/'docs/evidence.md').symlink_to('../local/proof.md')
   subprocess.run(['git','add','README.md','docs/evidence.md'],cwd=root,check=True)
   report=m.check(root)
   self.assertFalse(report['passed']);self.assertEqual(report['issues'][0]['kind'],'unpublished_target')
 def test_inline_code_examples_are_not_links_but_code_in_headings_is_preserved(self):
  m=self.module()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.repo(root);self.write(root,'README.md','# Project\n\n`[Example](missing.md)`\n``[Example `code`](also-missing.md)``\n[Real](docs/api.md#code-topic)\n');self.write(root,'docs/api.md','# API\n\n## `Code` topic\n')
   self.assertTrue(m.check(root)['passed'])

if __name__=='__main__':unittest.main()
