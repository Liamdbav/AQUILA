"""
Pipeline : fichier/dossier Python → exécutable protégé via Cython + PyInstaller.

Usage : python packager.py <input_path> <output_dir>
"""
import sys
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

STEP  = "STEP"
DONE  = "DONE"
ERROR = "ERROR"
INFO  = "INFO"

EXCLUDE_DIRS  = {"tests", "test", "__pycache__", ".venv", "venv", ".git", "dist", "build"}
EXCLUDE_FILES = {"setup.py", "conftest.py", "manage.py"}


def emit(status: str, message: str) -> None:
    print(f"{status}:{message}", flush=True)


# ── Détection du point d'entrée ────────────────────────────────────────────

def find_entry_point(directory: Path) -> tuple[Path, str | None]:
    """
    Retourne (fichier_entree, callable_ou_None).

    Ordre de priorité :
    1. Fichiers standards à la racine : main.py, app.py, __main__.py
    2. [project.scripts] dans pyproject.toml
    3. __main__.py dans un sous-paquet
    4. Fichier .py unique à la racine (hors setup/conftest)
    """
    for name in ("main.py", "app.py", "__main__.py"):
        if (directory / name).exists():
            return directory / name, None

    pyproject = directory / "pyproject.toml"
    if pyproject.exists():
        result = _entry_from_pyproject(pyproject, directory)
        if result:
            return result

    for f in sorted(directory.glob("*/__main__.py")):
        return f, None

    candidates = [
        f for f in directory.glob("*.py")
        if f.name not in EXCLUDE_FILES
    ]
    if len(candidates) == 1:
        return candidates[0], None

    found = [str(p.relative_to(directory)) for p in directory.rglob("*.py")
             if not any(part in EXCLUDE_DIRS for part in p.parts)][:8]
    raise FileNotFoundError(
        f"Aucun point d'entrée détecté dans {directory.name}/. "
        f"Fichiers .py trouvés : {found}"
    )


def _entry_from_pyproject(pyproject: Path, project_dir: Path) -> tuple[Path, str | None] | None:
    """Parse [project.scripts] → retourne (fichier, callable)."""
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    scripts = data.get("project", {}).get("scripts", {})
    if not scripts:
        return None

    spec = next(iter(scripts.values()))        # ex: "kontakt.cli:main"
    module_spec, _, callable_name = spec.partition(":")
    file_path = project_dir.joinpath(*module_spec.split(".")).with_suffix(".py")
    if file_path.exists():
        return file_path, callable_name or None
    return None


def _dependencies_from_pyproject(pyproject: Path) -> list[str]:
    """Retourne les noms de paquets déclarés dans [project.dependencies]."""
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        deps = data.get("project", {}).get("dependencies", [])
        names = []
        for dep in deps:
            m = re.match(r"^([A-Za-z0-9_-]+)", dep)
            if m:
                names.append(m.group(1).lower().replace("-", "_"))
        return names
    except Exception:
        return []


# ── Collecte des fichiers source ───────────────────────────────────────────

def collect_py_files(project_dir: Path) -> list[tuple[Path, str]]:
    """
    Retourne [(fichier, module.name)] pour tous les .py compilables du projet.
    Exclut tests, __pycache__, venvs, fichiers de config.
    """
    results = []
    for py_file in sorted(project_dir.rglob("*.py")):
        if any(part in EXCLUDE_DIRS for part in py_file.relative_to(project_dir).parts):
            continue
        if py_file.name in EXCLUDE_FILES:
            continue
        module_name = ".".join(py_file.relative_to(project_dir).with_suffix("").parts)
        results.append((py_file, module_name))
    return results


# ── Compilation Cython ─────────────────────────────────────────────────────

def cython_compile(py_file: Path, c_out: Path) -> bool:
    """Transpile .py → .c. Retourne False si Cython refuse le fichier (non bloquant)."""
    result = subprocess.run(
        [sys.executable, "-m", "cython", "--3str", str(py_file), "-o", str(c_out)],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def build_extension(module_name: str, c_file: Path, project_root: Path, build_tmp: Path) -> Path | None:
    """
    Compile .c → .so en respectant la hiérarchie du module_name.
    Le .so est placé dans project_root/a/b/c.cpython-3xx-darwin.so.
    Retourne None si la compilation échoue (non bloquant).
    """
    mini_setup = build_tmp / f"_s_{module_name.replace('.', '_')}.py"
    mini_setup.write_text(
        f"from setuptools import setup, Extension\n"
        f"setup(ext_modules=[Extension('{module_name}', [r'{c_file}'])])\n"
    )
    (build_tmp / "build").mkdir(exist_ok=True)

    result = subprocess.run(
        [
            sys.executable, str(mini_setup),
            "build_ext", "--inplace",
            f"--build-temp={build_tmp / 'build'}",
        ],
        capture_output=True, text=True, cwd=project_root,
    )
    if result.returncode != 0:
        return None

    stem = module_name.split(".")[-1]
    for ext in (".so", ".pyd"):
        for f in project_root.rglob(f"{stem}*{ext}"):
            return f
    return None


# ── Pipeline principal ─────────────────────────────────────────────────────

def run(input_path: str, output_dir: str) -> None:
    src = Path(input_path).resolve()
    out = Path(output_dir).resolve()

    if not src.exists():
        emit(ERROR, f"Chemin introuvable : {src}")
        sys.exit(1)

    # ── Résolution de l'entrée ───────────────────────────────────────────
    if src.is_dir():
        project_dir = src
        emit(STEP, f"Détection du point d'entrée dans {src.name}/")
        try:
            entry, entry_callable = find_entry_point(src)
        except FileNotFoundError as exc:
            emit(ERROR, str(exc))
            sys.exit(1)
    else:
        if src.suffix != ".py":
            emit(ERROR, f"Le fichier d'entrée doit être un .py, reçu : {src.name}")
            sys.exit(1)
        project_dir = src.parent
        entry = src
        entry_callable = None

    entry_rel = entry.relative_to(project_dir)
    emit(STEP, f"Point d'entrée : {entry_rel}")
    if entry_callable:
        emit(INFO, f"  callable : {entry_callable}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="aquila_"))
    emit(INFO, f"Répertoire temporaire : {tmp_dir}")

    try:
        # ── Copie du projet dans tmp_dir ─────────────────────────────────
        tmp_project = tmp_dir / "project"
        shutil.copytree(
            project_dir, tmp_project,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".venv", "venv", ".git",
                "tests", "test", "dist", "build", "*.egg-info",
            ),
        )

        # ── Collecte des dépendances externes (pyproject.toml) ───────────
        pyproject = tmp_project / "pyproject.toml"
        ext_deps = _dependencies_from_pyproject(pyproject) if pyproject.exists() else []
        if ext_deps:
            emit(INFO, f"  dépendances détectées : {', '.join(ext_deps)}")

        # ── Compilation Cython ────────────────────────────────────────────
        emit(STEP, "Compilation Cython en cours")
        build_tmp = tmp_dir / "build_tmp"
        build_tmp.mkdir()

        if src.is_dir():
            files = collect_py_files(tmp_project)
        else:
            # Fichier unique : compiler uniquement lui
            rel = entry.relative_to(project_dir)
            files = [(tmp_project / rel, rel.with_suffix("").name)]

        compiled_modules: list[str] = []
        for py_file, module_name in files:
            c_file = build_tmp / f"{module_name.replace('.', '_')}.c"
            ok = cython_compile(py_file, c_file)
            if not ok:
                emit(INFO, f"  ⚠ ignoré (Cython) : {module_name}")
                continue
            so = build_extension(module_name, c_file, tmp_project, build_tmp)
            if so:
                emit(INFO, f"  ✓ compilé : {module_name}")
                compiled_modules.append(module_name)
            else:
                emit(INFO, f"  ⚠ ignoré (build_ext) : {module_name}")

        # ── Génération du lanceur ─────────────────────────────────────────
        emit(STEP, "Génération du lanceur")
        entry_module = ".".join(entry_rel.with_suffix("").parts)
        launcher = tmp_dir / "_launcher.py"

        if entry_callable:
            # Package avec callable déclaré (ex: kontakt.cli:main)
            launcher.write_text(
                f"from {entry_module} import {entry_callable}\n"
                f"{entry_callable}()\n"
            )
        else:
            # Fichier/module direct
            launcher.write_text(
                "import sys, os\n"
                "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'project'))\n"
                f"import {entry_module}\n"
            )

        # ── PyInstaller ───────────────────────────────────────────────────
        emit(STEP, "Packaging PyInstaller en cours")
        dist_dir = tmp_dir / "dist"
        work_dir = tmp_dir / "work"
        exe_name = entry_callable or entry.stem

        hidden: list[str] = []
        for mod in compiled_modules:
            hidden += ["--hidden-import", mod]

        # Collecter les sous-modules des paquets compilés
        top_pkgs = {mod.split(".")[0] for mod in compiled_modules if "." in mod}
        collect_args: list[str] = []
        for pkg in top_pkgs:
            collect_args += ["--collect-submodules", pkg]

        # Collecter les dépendances externes pour que PyInstaller les trouve
        for dep in ext_deps:
            collect_args += ["--collect-all", dep]

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--noconsole",
            "--clean",
            f"--distpath={dist_dir}",
            f"--workpath={work_dir}",
            f"--specpath={tmp_dir}",
            f"--name={exe_name}",
            f"--paths={tmp_project}",
            *hidden,
            *collect_args,
            str(launcher),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout[-3000:])

        # ── Copie vers output_dir ─────────────────────────────────────────
        out.mkdir(parents=True, exist_ok=True)
        produced = next(
            (f for f in dist_dir.glob(f"{exe_name}*") if f.suffix != ".app"),
            next(dist_dir.glob(f"{exe_name}*"), None),
        )
        if produced is None:
            raise FileNotFoundError("Binaire introuvable dans dist/ après PyInstaller")

        final = out / produced.name
        shutil.copy2(str(produced), str(final))
        emit(DONE, str(final))

    except Exception as exc:
        emit(ERROR, str(exc))
        sys.exit(1)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage : python packager.py <input_path> <output_dir>", file=sys.stderr)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
