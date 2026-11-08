"""Create the authorized two-repository layout. Dry run unless --create/--push are explicitly supplied."""

import argparse, json, os, pathlib, re, shutil, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--owner", required=True)
p.add_argument("--public-name", default="veterinary-fieldnotes")
p.add_argument("--private-name", default="veterinary-fieldnotes-master")
p.add_argument(
    "--private-path", type=pathlib.Path, default=pathlib.Path(os.environ.get("FIELDNOTES_HOME", pathlib.Path.home() / "FieldNotes")).expanduser() / "repositories/master"
)
p.add_argument("--create", action="store_true")
p.add_argument("--push", action="store_true")
a = p.parse_args()
for name in [a.owner, a.public_name, a.private_name]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise SystemExit("Invalid GitHub name")
repos = [(ROOT, a.public_name, "public"), (a.private_path, a.private_name, "private")]
if not a.create:
    print(
        json.dumps(
            {
                "plan": [
                    {
                        "repo": a.owner + "/" + name,
                        "visibility": visibility,
                        "path": str(path),
                    }
                    for path, name, visibility in repos
                ],
                "next": "Authenticate with gh auth login, then repeat with --create. Add --push when the code is ready.",
            },
            indent=2,
        )
    )
    raise SystemExit(0)


def command(args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=capture)


user = json.loads(command(["gh", "api", "user"], capture=True).stdout)
for path, name, visibility in repos:
    full = a.owner + "/" + name
    if not path.exists():
        shutil.copytree(ROOT / "templates/private-master", path)
    if not (path / ".git").exists():
        command(["git", "init", "-b", "main"], cwd=path)
    command(["git", "config", "user.name", user["login"]], cwd=path)
    command(
        [
            "git",
            "config",
            "user.email",
            f"{user['id']}+{user['login']}@users.noreply.github.com",
        ],
        cwd=path,
    )
    result = subprocess.run(
        ["gh", "repo", "view", full, "--json", "visibility"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        command(
            [
                "gh",
                "repo",
                "create",
                full,
                "--" + visibility,
                "--description",
                "Source-linked veterinary learning system"
                if visibility == "public"
                else "Authorized master archive scaffold; no clinical data uploaded",
            ]
        )
    elif json.loads(result.stdout)["visibility"].lower() != visibility:
        raise SystemExit(
            "Existing repository has unexpected visibility; refusing to change it"
        )
    remote = "https://github.com/" + full + ".git"
    existing = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=path, capture_output=True, text=True
    )
    if existing.returncode:
        command(["git", "remote", "add", "origin", remote], cwd=path)
    elif existing.stdout.strip() != remote:
        raise SystemExit("Existing origin differs; refusing to change it")
    if a.push:
        if visibility == "private":
            allowed = ["README.md", ".gitignore"]
        else:
            allowed = [
                ".gitignore",
                ".prettierrc.json",
                ".github",
                "AGENTS.md",
                "README.md",
                "astro.config.mjs",
                "tsconfig.json",
                "package.json",
                "package-lock.json",
                "playwright.config.ts",
                "wrangler.toml",
                "src",
                "content",
                "fixtures/demo",
                "fixtures/pipeline",
                "schemas",
                "pipeline/pyproject.toml",
                "pipeline/uv.lock",
                "pipeline/vet_pipeline",
                "pipeline/tests",
                "scripts",
                "public",
                "tests",
                "docs",
                "config",
                "automation",
                "templates",
            ]
        command(["git", "add", "--", *allowed], cwd=path)
        staged = command(
            ["git", "diff", "--cached", "--name-only"], cwd=path, capture=True
        ).stdout.splitlines()
        for filename in staged:
            file = path / filename
            if not file.is_file():
                continue
            if (
                file.suffix.lower() in [".wav", ".mp3", ".flac", ".key"]
                or ".env" in file.name
                or ".venv" in file.parts
            ):
                raise SystemExit("Forbidden staged file: " + filename)
            raw = file.read_bytes()
            if re.search(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,})", raw):
                raise SystemExit("Possible credential in staged file: " + filename)
        if staged:
            command(
                ["git", "commit", "-m", "Build veterinary knowledge system foundation"],
                cwd=path,
            )
        command(["git", "push", "-u", "origin", "main"], cwd=path)
    print(
        json.dumps(
            {
                "repo": "https://github.com/" + full,
                "visibility": visibility,
                "pushed": a.push,
            }
        )
    )
