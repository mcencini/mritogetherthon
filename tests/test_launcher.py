"""The launchers the hub page offers, against a stand-in for Docker.

The shell launcher runs where ``sh`` does, the batch launcher on Windows.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
IMAGE = "ghcr.io/mcencini/mritogetherthon"

#: A stand-in for the docker command line, keeping the local image, the
#: published one, the container and every call in the JSON file DOCKER_STATE
#: names.
FAKE_DOCKER = r'''
import json, os, sys
path = os.environ["DOCKER_STATE"]
state = json.load(open(path))
argv = sys.argv[1:]
state["calls"].append(argv)
def done(code=0, out=""):
    json.dump(state, open(path, "w"))
    sys.stdout.write(out)
    sys.exit(code)
if not state["daemon"]:
    done(1)
if argv[0] == "info":
    done(0, "[name=seccomp,profile=builtin name=rootless]\n" if state.get("rootless") else "[name=seccomp,profile=builtin]\n")
if argv[:2] == ["image", "inspect"]:
    if not state["local"]:
        done(1)
    digests = "RepoDigests" in argv[argv.index("--format") + 1]
    done(0, ("ghcr.io/mcencini/mritogetherthon@" if digests else "") + state["local"] + "\n")
if argv[0] == "pull":
    if not state["published"]:
        done(1)
    state["local"] = state["published"]
    done()
if argv[0] == "inspect":
    if not state.get("container"):
        done(1)
    done(0, "true " + state["container"] + "\n")
if argv[0] == "rm":
    state["container"] = None
    done()
if argv[0] == "run":
    state["container"] = state["local"]
    done()
done(1)
'''

#: A stand-in for curl, for which JupyterLab always answers.
FAKE_CURL = "import sys; sys.exit(0)\n"


def _run(tmp_path, local, published, daemon=True, container=None, rootless=False, link=None):
    state = tmp_path / "docker.json"
    state.write_text(json.dumps({"daemon": daemon, "local": local, "published": published,
                                 "container": container, "rootless": rootless, "calls": []}))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "docker.py").write_text(FAKE_DOCKER)
    (bin_dir / "curl.py").write_text(FAKE_CURL)
    home = tmp_path / "home"
    work = tmp_path / "my work"
    if os.name == "nt":
        for tool in ("docker", "curl"):
            (bin_dir / f"{tool}.cmd").write_text(f'@"{sys.executable}" "%~dp0{tool}.py" %*\r\n')
        script = tmp_path / "mritogetherthon.bat"
        script.write_text((WEB / "mritogetherthon.bat").read_text().replace("\n", "\r\n"), newline="")
        command = ["cmd", "/c", str(script)]
        if link:
            command = f'cmd /s /c ""{script}" "{link}""'
    else:
        for tool in ("docker", "curl"):
            stand_in = bin_dir / tool
            stand_in.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{bin_dir / (tool + ".py")}" "$@"\n')
            stand_in.chmod(0o755)
        script = tmp_path / "mritogetherthon.sh"
        shutil.copy(WEB / "mritogetherthon.sh", script)
        command = ["sh", str(script)] + ([link] if link else [])
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "DOCKER_STATE": str(state), "MRITOGETHERTHON_HOME": str(home),
           "MRITOGETHERTHON_WORK": str(work), "MRITOGETHERTHON_NO_BROWSER": "1",
           "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
           "XDG_DATA_HOME": str(tmp_path / "share"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    env.pop("MRITOGETHERTHON_IMAGE", None)
    env.pop("MRITOGETHERTHON_PORT", None)
    done = subprocess.run(command, env=env, input="", capture_output=True, text=True, timeout=120)
    return done, json.loads(state.read_text())["calls"], home, work


def _output(done):
    return done.stdout + done.stderr


needs_shell = pytest.mark.skipif(os.name != "nt" and shutil.which("sh") is None, reason="needs sh")


@needs_shell
def test_an_absent_image_is_installed_and_started_on_the_attendee_s_folder(tmp_path):
    done, calls, home, work = _run(tmp_path, None, "sha256:new")

    assert done.returncode == 0, _output(done)
    assert "is not installed" in done.stdout
    assert "The environment is installed." in done.stdout
    assert ["pull", IMAGE] in calls
    run = calls[-1]
    assert run[0] == "run" and run[-1] == IMAGE
    assert "127.0.0.1:8899:8888" in run
    assert f"{work}:/home/mri" in run
    assert f"MRITOGETHERTHON_IMAGE={IMAGE}@sha256:new" in run
    token = (home / "token").read_text().strip()
    assert len(token) >= 32
    assert f"JUPYTER_TOKEN={token}" in run
    assert f"http://127.0.0.1:8899/lab?token={token}" in done.stdout
    assert work.is_dir()


@needs_shell
def test_an_outdated_image_is_updated_and_its_container_made_again(tmp_path):
    done, calls, _, _ = _run(tmp_path, "sha256:old", "sha256:new", container="sha256:old")

    assert done.returncode == 0, _output(done)
    assert "was outdated and is updated." in done.stdout
    assert ["rm", "-f", "mritogetherthon"] in calls
    assert calls[-1][0] == "run"


@needs_shell
def test_a_container_running_the_newest_image_keeps_running(tmp_path):
    done, calls, _, _ = _run(tmp_path, "sha256:new", "sha256:new", container="sha256:new")

    assert done.returncode == 0, _output(done)
    assert "is up to date." in done.stdout
    assert "already running" in done.stdout
    assert not any(call[0] in ("rm", "run") for call in calls)


@needs_shell
def test_an_installed_image_starts_when_the_registry_does_not_answer(tmp_path):
    done, calls, _, _ = _run(tmp_path, "sha256:old", None)

    assert done.returncode == 0, _output(done)
    assert "could not be checked" in done.stdout
    assert calls[-1][0] == "run"


@needs_shell
def test_docker_not_running_stops_before_anything_is_pulled(tmp_path):
    done, calls, _, _ = _run(tmp_path, None, "sha256:new", daemon=False)

    assert done.returncode == 1
    assert "not running" in done.stdout
    assert not any(call[0] == "pull" for call in calls)


@needs_shell
def test_the_token_is_kept_from_one_run_to_the_next(tmp_path):
    _, _, home, _ = _run(tmp_path, None, "sha256:old")
    first = (home / "token").read_text().strip()
    done, calls, _, _ = _run(tmp_path, "sha256:old", "sha256:new", container="sha256:old")

    assert done.returncode == 0, _output(done)
    assert f"JUPYTER_TOKEN={first}" in calls[-1]


@pytest.mark.skipif(os.name == "nt", reason="the shell launcher's users")
def test_the_container_runs_as_the_attendee_or_as_rootless_docker_s_root(tmp_path):
    done, calls, _, _ = _run(tmp_path, None, "sha256:new")
    assert done.returncode == 0, _output(done)
    run = calls[-1]
    assert run[run.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"

    rootless = tmp_path / "rootless"
    rootless.mkdir()
    done, calls, _, _ = _run(rootless, None, "sha256:new", rootless=True)
    assert done.returncode == 0, _output(done)
    run = calls[-1]
    assert run[run.index("--user") + 1] == "0:0"


@needs_shell
def test_the_launcher_copies_itself_where_the_open_button_s_handler_runs_it(tmp_path):
    done, _, home, _ = _run(tmp_path, "sha256:new", "sha256:new")

    assert done.returncode == 0, _output(done)
    copy = home / ("mritogetherthon.bat" if os.name == "nt" else "mritogetherthon.sh")
    assert "mritogetherthon" in copy.read_text()
    if os.name != "nt" and sys.platform != "darwin":
        entry = (tmp_path / "share" / "applications" / "mritogetherthon.desktop").read_text()
        assert "MimeType=x-scheme-handler/mritogetherthon;" in entry
        assert f'Exec=sh "{home / "mritogetherthon.sh"}" %u' in entry


@needs_shell
def test_an_open_link_starts_the_environment(tmp_path):
    done, calls, home, _ = _run(tmp_path, "sha256:new", "sha256:new", link="mritogetherthon:open")

    assert done.returncode == 0, _output(done)
    assert calls[-1][0] == "run"
    if os.name != "nt":
        assert "JupyterLab: http://127.0.0.1:8899/lab?token=" in (home / "launcher.log").read_text()
