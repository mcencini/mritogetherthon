#!/bin/sh
# The image's entry point. Without arguments, or with options alone, it serves
# JupyterLab from the attendee's home with those options after its own. Any
# other command runs in JupyterLab's place, as `bash` opens a shell.

# An empty home, the attendee's first start, is greeted with what to do first.
if [ -z "$(ls -A "$HOME" 2>/dev/null)" ]; then
    cp /usr/local/share/mritogetherthon/START_HERE.md "$HOME/" 2>/dev/null
fi
case "${1:-}" in
"" | -*)
    set -- jupyter lab "$@"
    ;;
esac
exec "$@"
