"""The attendee's commands, `team` and `submit`, and the update of the material.

They run against two local repositories standing in for the organisers' two
repositories, the environment's (the hands-on material) and the pipeline's (the
teams' forks), and a stand-in for the GitHub command line that keeps the forks
in folders and the invitations and pull requests in files.
"""

import os
import subprocess
from pathlib import Path

import pytest

DOCKER = Path(__file__).resolve().parent.parent / "docker"

#: A stand-in for `gh`, logged in as $GH_LOGIN.
FAKE_GH = r'''#!/bin/sh
echo "$*" >> "$CALLS"
case "$*" in
"auth status") [ -n "$GH_LOGIN" ]; exit $? ;;
"auth setup-git") exit 0 ;;
"api user --jq .login") echo "$GH_LOGIN" ;;
"api user --jq .name // .login") echo "$GH_LOGIN" ;;
"api user --jq "*) echo "1+$GH_LOGIN@users.noreply.github.com" ;;
repo\ fork*--remote*) echo "the --remote flag is unsupported when a repository argument is provided" >&2; exit 1 ;;
repo\ fork*) mkdir -p "$FORKS/$GH_LOGIN"
    [ -d "$FORKS/$GH_LOGIN/pipeline.git" ] || git clone -q --bare "$PIPELINE_DIR" "$FORKS/$GH_LOGIN/pipeline.git" ;;
api\ -X\ PUT*) exit 0 ;;
api\ user/repository_invitations\ *) echo 5 ;;
api\ -X\ PATCH*) exit 0 ;;
pr\ list*) [ -f "$PRS" ] && cat "$PRS"; exit 0 ;;
pr\ create*) echo "https://github.com/org/pipeline/pull/1" | tee "$PRS" ;;
*) echo "unexpected: $*" >&2; exit 1 ;;
esac
'''


def git(*args, cwd):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def repository(path, files):
    path.mkdir()
    git("init", "-q", "-b", "main", cwd=path)
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    git("add", "-A", cwd=path)
    git("commit", "-qm", "start", cwd=path)
    return path


@pytest.fixture
def world(tmp_path):
    material = repository(tmp_path / "material", {
        "handson/day1/notebook.txt": "{}\n", "handson/day1/README.md": "tutors' note\n",
        "data/phantoms/p1.phantom": "p\n", "answers/day1/notebook.txt": "{}\n", "docker/Dockerfile": "not material\n"})
    pipeline = repository(tmp_path / "pipeline", {"stages/sequence/README.md": "contract\n"})

    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "gh").write_text(FAKE_GH)
    (bin / "gh").chmod(0o755)
    for name in ("sync-material", "github-login", "team", "submit"):
        (bin / name).symlink_to(DOCKER / name)
    (tmp_path / "forks").mkdir()
    (tmp_path / "calls").write_text("")

    def member(login):
        """A member's computer: their own home, logged in as `login`, or with
        an empty one to no GitHub account."""
        home = tmp_path / f"home-{login or 'nobody'}"
        home.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin}:{os.environ['PATH']}",
            "MATERIAL_URL": f"file://{material}",
            "PIPELINE_REPO": "org/pipeline",
            "GITHUB_URL": f"file://{tmp_path}/forks",
            "PIPELINE_DIR": str(pipeline),
            "FORKS": str(tmp_path / "forks"),
            "PRS": str(tmp_path / "prs"),
            "CALLS": str(tmp_path / "calls"),
            "GH_LOGIN": login,
        }

        def run(*command):
            return subprocess.run(command, env=env, capture_output=True, text=True, cwd=home)

        return home, run

    return material, tmp_path, member


def test_the_material_is_downloaded_whole_and_read_only(world):
    _, _, member = world
    home, run = member("alice")
    done = run("sync-material")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (home / "material/handson/day1/notebook.txt").exists()
    assert (home / "material/data/phantoms/p1.phantom").exists()
    assert not (home / "material/docker").exists()
    assert not os.access(home / "material/handson/day1/notebook.txt", os.W_OK) or os.geteuid() == 0


def test_the_material_follows_the_organisers(world):
    material, _, member = world
    home, run = member("alice")
    run("sync-material")
    (material / "handson/day1/notebook.txt").write_text('{"fixed": 1}\n')
    (material / "handson/day2").mkdir()
    (material / "handson/day2/notebook.txt").write_text("{}\n")
    git("add", "-A", cwd=material)
    git("commit", "-qm", "fix and day 2", cwd=material)
    done = run("sync-material")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (home / "material/handson/day1/notebook.txt").read_text() == '{"fixed": 1}\n'
    assert (home / "material/handson/day2/notebook.txt").exists()


def test_the_first_member_forks_and_gets_the_notebooks(world):
    _, tmp_path, member = world
    home, run = member("alice")
    done = run("team", "07")
    assert done.returncode == 0, done.stdout + done.stderr
    team = home / "team"
    assert git("remote", "get-url", "origin", cwd=team).endswith("forks/alice/pipeline.git")
    assert git("config", "--get", "mritogether.team", cwd=team) == "07"
    assert (team / "day1/notebook.txt").exists() and not (team / "day1/README.md").exists()
    assert os.access(team / "day1/notebook.txt", os.W_OK)
    assert (team / "stages/sequence/README.md").exists()
    assert (home / "material/answers/day1/notebook.txt").exists()  # in the material
    assert not (team / "answers").exists()                            # but not in the team's folder
    # A plain push goes to the fork.
    (team / "day1/notebook.txt").write_text('{"alice": 1}\n')
    git("add", "-A", cwd=team)
    git("commit", "-qm", "by hand", cwd=team)
    git("push", "-q", cwd=team)
    assert "by hand" in git("log", "--format=%s", "main", cwd=tmp_path / "forks/alice/pipeline.git")


def test_a_team_needs_a_two_digit_number(world):
    assert world[2]("alice")[1]("team", "7").returncode == 2


def test_the_lead_invites_teammates(world):
    _, tmp_path, member = world
    _, run = member("alice")
    run("team", "07")
    done = run("team", "add", "bob", "carol")
    assert done.returncode == 0, done.stdout + done.stderr
    calls = (tmp_path / "calls").read_text()
    assert "repos/alice/pipeline/collaborators/bob" in calls
    assert "repos/alice/pipeline/collaborators/carol" in calls


def test_a_teammate_joins_the_fork_with_or_without_an_account(world):
    _, tmp_path, member = world
    home, run = member("alice")
    run("team", "07")
    team = home / "team"
    (team / "day1/notebook.txt").write_text('{"alice": 1}\n')
    git("add", "-A", cwd=team)
    git("commit", "-qm", "alice's work", cwd=team)
    git("push", "-q", cwd=team)

    bob_home, bob = member("bob")
    done = bob("team", "07", "alice")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (bob_home / "team/day1/notebook.txt").read_text() == '{"alice": 1}\n'
    assert "PATCH" in (tmp_path / "calls").read_text()  # the invitation is accepted

    guest_home, guest = member("")
    done = guest("team", "07", "alice")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (guest_home / "team/day1/notebook.txt").read_text() == '{"alice": 1}\n'
    assert "without an account" in done.stdout


def test_an_update_never_touches_what_the_team_has(world):
    material, _, member = world
    home, run = member("alice")
    run("team", "07")
    mine = home / "team/day1/notebook.txt"
    mine.write_text('{"mine": 1}\n')
    (material / "handson/day1/notebook.txt").write_text('{"tutor": 1}\n')
    (material / "handson/day2").mkdir()
    (material / "handson/day2/notebook.txt").write_text("{}\n")
    git("add", "-A", cwd=material)
    git("commit", "-qm", "changes", cwd=material)
    done = run("sync-material")
    assert done.returncode == 0, done.stdout + done.stderr
    assert mine.read_text() == '{"mine": 1}\n'                                  # the team's own notebook
    assert (home / "team/day2/notebook.txt").exists()                          # a new one is copied
    assert (home / "material/handson/day1/notebook.txt").read_text() == '{"tutor": 1}\n'
    assert git("status", "--porcelain", cwd=home / "team")                       # as untracked: nothing committed for them
    assert git("log", "--format=%s", cwd=home / "team").split("\n") == ["Team 07: the notebooks to start from", "start"]


def test_submit_pushes_to_the_fork_and_opens_one_pull_request_to_the_teams_branch(world):
    _, tmp_path, member = world
    home, run = member("alice")
    run("team", "07")
    (home / "team/day1/notebook.txt").write_text('{"mine": 1}\n')
    done = run("submit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "pull/1" in done.stdout
    assert "--base team-07" in (tmp_path / "calls").read_text()
    fork = tmp_path / "forks/alice/pipeline.git"
    assert git("show", "main:day1/notebook.txt", cwd=fork) == '{"mine": 1}'
    # A second submission pushes to the same fork, and finds the pull request.
    (home / "team/day1/notebook.txt").write_text('{"mine": 2}\n')
    done = run("submit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert git("show", "main:day1/notebook.txt", cwd=fork) == '{"mine": 2}'
    assert (tmp_path / "calls").read_text().count("pr create") == 1


def test_submit_needs_a_team(world):
    assert world[2]("alice")[1]("submit").returncode == 1


def test_a_notebook_the_fork_has_is_not_copied_over_it(world):
    material, _, member = world
    alice_home, alice = member("alice")
    alice("team", "07")
    bob_home, bob = member("bob")
    bob("team", "07", "alice")
    (material / "handson/day2").mkdir()
    (material / "handson/day2/notebook.txt").write_text("{}\n")
    git("add", "-A", cwd=material)
    git("commit", "-qm", "day 2", cwd=material)
    alice("sync-material")
    (alice_home / "team/day2/notebook.txt").write_text('{"alice": 1}\n')
    git("add", "-A", cwd=alice_home / "team")
    git("commit", "-qm", "alice's day 2", cwd=alice_home / "team")
    git("push", "-q", cwd=alice_home / "team")
    bob("sync-material")
    assert not (bob_home / "team/day2").exists()
    git("pull", "-q", "--no-rebase", cwd=bob_home / "team")
    assert (bob_home / "team/day2/notebook.txt").read_text() == '{"alice": 1}\n'


def test_two_copies_of_a_new_notebook_collide_without_losing_either(world):
    material, _, member = world
    alice_home, alice = member("alice")
    alice("team", "07")
    bob_home, bob = member("bob")
    bob("team", "07", "alice")
    (material / "handson/day2").mkdir()
    (material / "handson/day2/notebook.txt").write_text("{}\n")
    git("add", "-A", cwd=material)
    git("commit", "-qm", "day 2", cwd=material)
    alice("sync-material")
    bob("sync-material")  # before alice has pushed hers
    (alice_home / "team/day2/notebook.txt").write_text('{"alice": 1}\n')
    git("add", "-A", cwd=alice_home / "team")
    git("commit", "-qm", "alice's day 2", cwd=alice_home / "team")
    git("push", "-q", cwd=alice_home / "team")
    (bob_home / "team/day2/notebook.txt").write_text('{"bob": 1}\n')
    pull = subprocess.run(["git", "pull", "-q", "--no-rebase"], cwd=bob_home / "team", capture_output=True, text=True)
    assert pull.returncode != 0
    assert (bob_home / "team/day2/notebook.txt").read_text() == '{"bob": 1}\n'
