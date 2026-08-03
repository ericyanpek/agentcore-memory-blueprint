#!/usr/bin/env bash
# Install the repository's git hooks.
#
# Hooks are not cloned with a repository, so each checkout has to install them once:
#
#     ./scripts/install_hooks.sh
#
# The hook is written to .git/hooks/ rather than via core.hooksPath, because on managed
# machines core.hooksPath may already point at a corporate hooks directory (git-defender,
# for example). Overwriting it would disable those checks. Repository-local hooks in
# .git/hooks/ still run in that setup.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Deliberately not `rev-parse --git-path hooks`: that resolves to core.hooksPath when it is
# set, which on a managed machine is a root-owned corporate directory we must not write to.
HOOK_DIR="$(git -C "$ROOT" rev-parse --absolute-git-dir)/hooks"
HOOK="$HOOK_DIR/pre-commit"

mkdir -p "$HOOK_DIR"

if [ -e "$HOOK" ] && ! grep -q "check_doc_alignment" "$HOOK" 2>/dev/null; then
  cp "$HOOK" "$HOOK.backup-$(date +%s)"
  echo "Existing pre-commit hook backed up alongside it."
fi

cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
# Reject a commit that leaves a bilingual document pair out of sync.
#
# Documentation is maintained in Chinese and English, and updating one side only is easy
# to do by accident. The drift stays invisible until someone reads the stale half, so it
# is worth catching at commit time rather than in review.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CHECKER="$ROOT/scripts/check_doc_alignment.py"

[ -f "$CHECKER" ] || exit 0

# Only run when documentation is actually part of this commit.
if ! git diff --cached --name-only --diff-filter=ACMR |
     grep -qE '(^|/)(README|SECURITY)[^/]*\.md$|(^|/)docs/.*\.md$|SKILL[^/]*\.md$'; then
  exit 0
fi

if ! python3 "$CHECKER"; then
  cat <<'MESSAGE'

Commit rejected: a bilingual document pair is out of sync.

Every document exists in Chinese and English (see CLAUDE.md). Update both sides in
the same commit, then commit again.

  python3 scripts/check_doc_alignment.py    # see the specific divergence

If the divergence is intentional and correct, record why in the commit message and
bypass this check with:

  CODE_DEFENDER_SKIP_LOCAL_HOOKS=true git commit ...

Prefer that over `git commit --no-verify`, which on a managed machine also skips the
corporate security scan rather than just this check.

MESSAGE
  exit 1
fi
HOOK_BODY

chmod +x "$HOOK"
echo "Installed pre-commit hook at $HOOK"
echo "It runs scripts/check_doc_alignment.py when a commit touches documentation."
