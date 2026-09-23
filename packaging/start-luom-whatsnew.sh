#!/bin/sh
# ---------------------------------------------------------------------------
#  Starts LUOM What's New (LUOM-WhatsNew.pyz in this folder) on macOS/Linux -
#  a free, independent LUOM community tool that indexes and links to WeCreat's
#  public knowledge base. LUOM does not maintain that knowledge base and is not
#  affiliated with WeCreat.
#
#  Needs Python 3.8 or newer. If it is missing, offers to install it -
#  Homebrew on macOS, the system package manager on Linux - and only after
#  you answer yes.
#
#  Any arguments are passed on, e.g.:  ./start-luom-whatsnew.sh scan
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1
APP="./LUOM-WhatsNew.pyz"

if [ ! -f "$APP" ]; then
    echo "LUOM-WhatsNew.pyz was not found next to this script ($(pwd))."
    echo "Keep the two files together in the same folder."
    exit 1
fi

find_python() {
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
            PY=$candidate
            return 0
        fi
    done
    return 1
}

ask() {  # ask "question" -> 0 for yes
    printf '%s [y/N] ' "$1"
    read -r answer
    case "$answer" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

if ! find_python; then
    echo
    echo "LUOM What's New needs Python 3.8 or newer, and it was not found."
    echo
    if [ "$(uname -s)" = "Darwin" ]; then
        if command -v brew >/dev/null 2>&1 && ask "Install Python now with Homebrew (brew install python)?"; then
            brew install python
        else
            echo "Install Python from https://www.python.org/downloads/macos/ , then run this again."
            open "https://www.python.org/downloads/macos/" 2>/dev/null
            exit 1
        fi
    else
        if command -v apt-get >/dev/null 2>&1; then INSTALL="sudo apt-get install -y python3"
        elif command -v dnf >/dev/null 2>&1; then INSTALL="sudo dnf install -y python3"
        elif command -v zypper >/dev/null 2>&1; then INSTALL="sudo zypper install -y python3"
        elif command -v pacman >/dev/null 2>&1; then INSTALL="sudo pacman -S --noconfirm python"
        else INSTALL=""
        fi
        if [ -n "$INSTALL" ] && ask "Install Python now with: $INSTALL ?"; then
            $INSTALL
        else
            echo "Install Python 3 with your system's package manager, then run this again."
            exit 1
        fi
    fi
    if ! find_python; then
        echo "Python is still not available. Open a new terminal and run this again."
        exit 1
    fi
fi

exec "$PY" "$APP" "$@"
