#!/bin/sh
# Installs, updates and starts the MRI TogetherThon's environment in Docker,
# and opens JupyterLab in the browser:
#
#   sh mritogetherthon.sh
#
# Your work lives in ~/mritogetherthon (MRITOGETHERTHON_WORK names another
# folder), which is the home folder you see in JupyterLab, so that it outlives
# the container and every update of the image.
#
# Run so, it also copies itself to ~/.mritogetherthon and registers that copy
# as the handler of mritogetherthon: links, which the hub page's "Open
# JupyterLab" button opens: from then on that button starts the environment,
# or updates it, and opens JupyterLab. Run with such a link, it writes its
# messages to ~/.mritogetherthon/launcher.log.
IMAGE=${MRITOGETHERTHON_IMAGE:-ghcr.io/mcencini/mritogetherthon}
NAME=mritogetherthon
PORT=${MRITOGETHERTHON_PORT:-8899}
HOME_DIR=${MRITOGETHERTHON_HOME:-$HOME/.mritogetherthon}
WORK=${MRITOGETHERTHON_WORK:-$HOME/mritogetherthon}

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed: install it from https://docs.docker.com/get-started/get-docker/ and run this again."
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "Docker is installed but not running: start Docker Desktop, or the Docker service, and run this again."
    exit 1
fi

install_handler() {
    cp "$0" "$HOME_DIR/mritogetherthon.sh" 2>/dev/null
    if [ "$(uname)" = Darwin ]; then
        app="$HOME/Applications/mritogetherthon.app"
        mkdir -p "$HOME/Applications"
        rm -rf "$app"
        cat > "$HOME_DIR/handler.applescript" <<SCRIPT
on open location address
	do shell script "PATH=\$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:\$PATH; sh " & quoted form of "$HOME_DIR/mritogetherthon.sh" & " " & quoted form of address & " >/dev/null 2>&1 &"
end open location
SCRIPT
        osacompile -o "$app" "$HOME_DIR/handler.applescript" || return
        /usr/libexec/PlistBuddy -c 'Add :LSUIElement bool true' -c 'Add :CFBundleURLTypes array' \
            -c 'Add :CFBundleURLTypes:0 dict' -c 'Add :CFBundleURLTypes:0:CFBundleURLName string mritogetherthon' \
            -c 'Add :CFBundleURLTypes:0:CFBundleURLSchemes array' \
            -c 'Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string mritogetherthon' "$app/Contents/Info.plist"
        codesign --force --sign - "$app" 2>/dev/null
        /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"
    else
        apps=${XDG_DATA_HOME:-$HOME/.local/share}/applications
        mkdir -p "$apps"
        cat > "$apps/mritogetherthon.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=MRI TogetherThon
Exec=sh "$HOME_DIR/mritogetherthon.sh" %u
NoDisplay=true
MimeType=x-scheme-handler/mritogetherthon;
ENTRY
        command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" 2>/dev/null
        command -v xdg-mime >/dev/null 2>&1 && xdg-mime default mritogetherthon.desktop x-scheme-handler/mritogetherthon
    fi
    echo "The hub page's Open JupyterLab button now starts the environment."
}

mkdir -p "$HOME_DIR" "$WORK"
case $1 in
mritogetherthon:*)
    exec >"$HOME_DIR/launcher.log" 2>&1
    ;;
*)
    install_handler
    ;;
esac

# The token JupyterLab asks for, made once and kept, so that a bookmark of
# JupyterLab's address keeps working.
if [ ! -s "$HOME_DIR/token" ]; then
    od -An -N16 -tx1 /dev/urandom | tr -d ' \n' > "$HOME_DIR/token"
fi
TOKEN=$(cat "$HOME_DIR/token")

before=$(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null)
if [ -z "$before" ]; then
    echo "The environment is not installed: downloading $IMAGE (several GB, once)."
else
    echo "The environment is installed: checking for a newer version."
fi
if ! docker pull "$IMAGE"; then
    if [ -z "$before" ]; then
        echo "The environment could not be downloaded."
        exit 1
    fi
    echo "The newest version could not be checked: starting the installed one."
fi
after=$(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null)
if [ -z "$before" ]; then
    echo "The environment is installed."
elif [ "$before" = "$after" ]; then
    echo "The environment is up to date."
else
    echo "The environment was outdated and is updated."
fi

# A container already running the newest image is left as it is, so that the
# notebooks' kernels keep running; any other is made again, with the work kept.
running=$(docker inspect --format '{{.State.Running}} {{.Image}}' "$NAME" 2>/dev/null)
if [ "$running" = "true $after" ]; then
    echo "The environment is already running."
else
    digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null)
    # Files in your folder belong to you: the container runs as your own user,
    # except under rootless Docker, whose root already is you.
    if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
        user=0:0
    else
        user="$(id -u):$(id -g)"
    fi
    docker rm -f "$NAME" >/dev/null 2>&1
    docker run -d --restart unless-stopped --name "$NAME" -p "127.0.0.1:$PORT:8888" \
        --user "$user" -e "JUPYTER_TOKEN=$TOKEN" -e "MRITOGETHERTHON_IMAGE=$digest" \
        -v "$WORK:/home/mri" "$IMAGE" >/dev/null || exit 1
    echo "The environment is running, with your work in $WORK."
fi

URL="http://127.0.0.1:$PORT/lab?token=$TOKEN"
if command -v curl >/dev/null 2>&1; then
    tries=0
    until curl -fs -o /dev/null "http://127.0.0.1:$PORT/api"; do
        tries=$((tries + 1))
        if [ "$tries" -gt 60 ]; then
            echo "JupyterLab does not answer: see  docker logs $NAME"
            exit 1
        fi
        sleep 2
    done
fi
echo "JupyterLab: $URL"
if [ -n "$MRITOGETHERTHON_NO_BROWSER" ]; then :
elif [ "$(uname)" = Darwin ]; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1
fi
