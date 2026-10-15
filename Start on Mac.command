#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python_bin=''
for candidate in "${commands[python3]:-}" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [[ -n "$candidate" && -x "$candidate" ]] || continue
  if "$candidate" -B -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' 2>/dev/null; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  print 'Python 3.9 or later is required. Install Python for macOS from https://www.python.org/downloads/macos/ and try again.'
  read '?Press Return to close.'
  exit 1
fi
if ! "$python_bin" -B -c 'import installer; raise SystemExit(not bool(installer.resolve_sdb()))' 2>/dev/null; then
  "$python_bin" -B installer.py --setup || { read '?Setup failed. Press Return to close.'; exit 1; }
fi
"$python_bin" -B installer.py
read '?Press Return to close.'
