#!/bin/sh
# The image's entry point. Without arguments, or with options alone, it serves
# JupyterLab from the attendee's home with those options after its own. Any
# other command runs in JupyterLab's place, as `bash` opens a shell.

# An empty home, the attendee's first start, is greeted with what to do first.
if [ -z "$(ls -A "$HOME" 2>/dev/null)" ]; then
    cp /usr/local/share/mritogetherthon/START_HERE.md "$HOME/" 2>/dev/null
fi
# The hands-on material is downloaded on the first start and replaced by the
# organisers' latest on every one. The container runs for days, so it also looks
# for their changes every half hour: a tutor's fix and the answers published after
# a session arrive without a restart.
sync-material
( while sleep "${MATERIAL_SYNC_SECONDS:-1800}"; do sync-material >/dev/null 2>&1; done ) &
case "${1:-}" in
"" | -*)
    set -- jupyter lab "$@"
    ;;
esac
exec "$@"
