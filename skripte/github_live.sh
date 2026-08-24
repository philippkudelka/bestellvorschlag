#!/bin/sh
# Veroeffentlicht das Repository auf GitHub und schaltet die statische Demo
# (docs/) als GitHub-Pages-Seite live. Voraussetzung: `gh auth login` wurde
# einmal ausgefuehrt.
set -e
cd "$(dirname "$0")/.."

if ! gh auth status >/dev/null 2>&1; then
  echo "Bitte zuerst anmelden:  gh auth login"
  exit 1
fi

KONTO=$(gh api user -q .login)
NAME="bestellvorschlag"

if ! gh repo view "$KONTO/$NAME" >/dev/null 2>&1; then
  echo "Erzeuge oeffentliches Repository $KONTO/$NAME und schiebe main ..."
  gh repo create "$NAME" --public --source . --push \
    --description "Bestellvorschlag fuer eine Handwerksbaeckerei — Demo mit simulierten Daten"
else
  echo "Repository existiert — schiebe main ..."
  git push -u origin main 2>/dev/null || {
    git remote add origin "https://github.com/$KONTO/$NAME.git"
    git push -u origin main
  }
fi

echo "Schalte GitHub Pages auf main:/docs ..."
gh api "repos/$KONTO/$NAME/pages" -X POST \
  -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 \
  || gh api "repos/$KONTO/$NAME/pages" -X PUT \
       -f "source[branch]=main" -f "source[path]=/docs" >/dev/null

echo ""
echo "Fertig. Die Demo erscheint in 1-2 Minuten unter:"
echo "  https://$KONTO.github.io/$NAME/"
echo "Repository:  https://github.com/$KONTO/$NAME"
