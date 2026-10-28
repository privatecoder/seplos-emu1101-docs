#!/usr/bin/env python3
"""Check public Markdown against Git-visible paths, independently of private data.

By default, inspect tracked and non-ignored new files in the working tree.
--index-only restricts eligibility to tracked index paths. Relative file,
directory and heading targets are checked; symlinks are ineligible. External URLs
are counted, not fetched.
No firmware, native emulator, serial transport or network is accessed.
"""
from pathlib import Path
import argparse
import collections
import json
import posixpath
import re
import subprocess
import unicodedata
import urllib.parse

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def un_fenced(text):
 lines=[];fence=None
 for number,line in enumerate(text.splitlines(),1):
  m=re.match(r'^ {0,3}(`{3,}|~{3,})',line)
  if m:
   mark=m[1]
   if fence is None:fence=(mark[0],len(mark))
   elif mark[0]==fence[0] and len(mark)>=fence[1]:fence=None
   lines.append((number,''));continue
  lines.append((number,line if fence is None else ''))
 return lines

def headings(path):
 result=[];counts=collections.Counter()
 for _,line in un_fenced(path.read_text()):
  m=re.match(r'^ {0,3}#{1,6}\s+(.+?)(?:\s+#+\s*)?$',line)
  if not m:continue
  name=re.sub(r'\[([^]]+)\]\([^)]*\)',r'\1',m[1])
  name=re.sub(r'<[^>]*>','',name).lower().strip()
  name=name.replace('`','').replace('*','').replace('\\','')
  name=''.join(c for c in name if c in '-_ ' or unicodedata.category(c)[0] in 'LN')
  slug=name.replace(' ','-');n=counts[slug];counts[slug]+=1
  result.append(slug+(f'-{n}' if n else ''))
 return set(result)

def without_inline_code(text):
    # Match equal backtick runs; preserve heading code text by using this only
    # while scanning links, not while calculating GitHub heading anchors.
    return re.sub(r'(?<!\\)(`+)(?!`)(.*?)(?<!`)\1(?!`)',
                  lambda match: ' ' * len(match.group()), text)


def links(text):
 for number,line in un_fenced(text):
  line=without_inline_code(line)
  pos=0
  while True:
   at=line.find('](',pos)
   if at<0:break
   at+=2;i=at;depth=1;angled=False
   while i<len(line):
    ch=line[i]
    if ch=='\\':i+=2;continue
    if ch=='<' and i==at:angled=True
    if ch=='>' and angled:angled=False
    elif not angled:
     if ch=='(':depth+=1
     if ch==')':
      depth-=1
      if depth==0:break
    i+=1
   if depth:break
   raw=line[at:i].strip();pos=i+1
   if raw.startswith('<'):
    end=raw.find('>');target=raw[1:end] if end>=0 else raw
   else:target=re.split(r'\s+[\"\']',raw,maxsplit=1)[0]
   yield number,target
  m=re.match(r'^ {0,3}\[[^]]+\]:\s*(<[^>]+>|\S+)',line)
  if m:yield number,m[1].strip('<>')

def public_paths(project, index_only=False):
    top = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=project).decode().strip()
    if Path(top).resolve() != Path(project).resolve():
        raise ValueError('--project must be the repository root')
    args = ['git', 'ls-files', '--cached', '--full-name', '-z']
    if not index_only:
        args += ['--others', '--exclude-standard']
    raw = subprocess.check_output(args, cwd=project)
    names = {name.decode('utf-8') for name in raw.split(b'\0') if name}
    return {name for name in names if not (project/name).is_symlink() and (project/name).is_file()}


def check(project, index_only=False):
    project = Path(project).resolve()
    public = public_paths(project, index_only)
    directories = {str(parent) for name in public for parent in Path(name).parents}
    issues = []
    counts = collections.Counter()
    anchor_cache = {}
    for name in sorted(name for name in public if name.lower().endswith('.md')):
        counts['markdown_files'] += 1
        for number, url in links((project/name).read_text(encoding='utf-8')):
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme or url.startswith('//'):
                counts['external_links'] += 1
                continue
            path = urllib.parse.unquote(parsed.path)
            anchor = urllib.parse.unquote(parsed.fragment)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
            item = {'file': name, 'line': number, 'link': url, 'target': target}
            if path.startswith('/') or target == '..' or target.startswith('../'):
                issues.append({**item, 'kind': 'outside_project'})
                continue
            if target not in public and target not in directories:
                issues.append({**item, 'kind': 'unpublished_target'})
                continue
            counts['relative_links'] += 1
            if anchor and target.lower().endswith('.md'):
                if target not in anchor_cache:
                    anchor_cache[target] = headings(project/target)
                if anchor not in anchor_cache[target]:
                    issues.append({**item, 'kind': 'missing_anchor'})
    return {'passed': not issues, 'mode': 'index-paths' if index_only else 'public-worktree-candidates',
            'counts': dict(counts), 'issues': issues,
            'scope': 'Only regular Git-visible files are eligible; symlinks and ignored private files cannot satisfy links. New non-ignored worktree files count by default. External URL availability is not checked.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=PROJECT_ROOT)
    parser.add_argument('--index-only', action='store_true', help='Use tracked index paths only; ignores untracked new files')
    parser.add_argument('--out', type=Path, help='Fresh optional JSON report; never overwrite an existing file')
    args = parser.parse_args(argv)
    if args.out and (args.out.exists() or args.out.is_symlink()):
        parser.error('Report already exists; choose a fresh path')
    try:
        report = check(args.project, args.index_only)
        if args.out:
            with args.out.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, indent=2)
                stream.write('\n')
        print(json.dumps(report, indent=2))
        return int(not report['passed'])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, 'Markdown check failed: '+str(error)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
