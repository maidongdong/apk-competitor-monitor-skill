#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path


def run(cmd, cwd=None, env=None, timeout=None):
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[-4000:],
        "stderr": completed.stderr.strip()[-4000:],
    }


def count_java_files(path):
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob("*.java"))


def find_vineflower_jar():
    env_value = os.environ.get("VINEFLOWER_JAR_PATH") or os.environ.get("FERNFLOWER_JAR_PATH")
    candidates = [
        env_value,
        str(Path.home() / "vineflower.jar"),
        str(Path.home() / "fernflower.jar"),
        str(Path.home() / "vineflower" / "build" / "libs" / "vineflower.jar"),
        str(Path.home() / "fernflower" / "build" / "libs" / "fernflower.jar"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def find_dex2jar():
    return shutil.which("d2j-dex2jar") or shutil.which("d2j-dex2jar.sh")


def extract_nested_apks(apk, output_dir):
    nested = []
    with zipfile.ZipFile(apk) as zf:
        for name in zf.namelist():
            if name.endswith(".apk"):
                out = output_dir / "nested-apks" / Path(name).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(zf.read(name))
                nested.append(str(out))
    return nested


def run_jadx(apk, out_dir, deobf=False, no_res=True):
    if not shutil.which("jadx"):
        return {"status": "missing", "java_files": 0, "detail": "jadx not found"}
    args = ["jadx", "-q", "-d", str(out_dir)]
    if no_res:
        args.append("--no-res")
    if deobf:
        args.append("--deobf")
    args.append(str(apk))
    result = run(args)
    java_count = count_java_files(out_dir)
    status = "ok" if result["returncode"] == 0 else "partial" if java_count else "failed"
    return {"status": status, "java_files": java_count, "detail": result}


def run_vineflower(apk, out_dir, timeout_seconds):
    jar = find_vineflower_jar()
    dex2jar = find_dex2jar()
    if not jar:
        return {"status": "missing", "java_files": 0, "detail": "Vineflower/Fernflower jar not found"}
    if not dex2jar:
        return {"status": "missing", "java_files": 0, "detail": "dex2jar not found"}

    intermediate = out_dir / "intermediate"
    intermediate.mkdir(parents=True, exist_ok=True)
    converted = intermediate / f"{apk.stem}-dex2jar.jar"
    convert_result = run([dex2jar, "-f", "-o", str(converted), str(apk)])
    if not converted.exists():
        return {"status": "failed", "java_files": 0, "detail": convert_result}

    sources_dir = out_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    ff_result = run(["java", "-jar", str(jar), "-dgs=1", "-mpm=60", str(converted), str(sources_dir)], timeout=timeout_seconds)
    java_count = count_java_files(sources_dir)
    status = "ok" if ff_result["returncode"] == 0 else "partial" if java_count else "failed"
    return {
        "status": status,
        "java_files": java_count,
        "intermediate_jar": str(converted),
        "convert": convert_result,
        "detail": ff_result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("apk")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--engine", choices=["jadx", "vineflower", "both"], default="both")
    parser.add_argument("--deobf", action="store_true")
    parser.add_argument("--include-res", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    apk = Path(args.apk).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    nested_apks = extract_nested_apks(apk, out_dir)
    results = {
        "apk": str(apk),
        "out_dir": str(out_dir),
        "engine": args.engine,
        "nested_apks": nested_apks,
        "engines": {},
    }
    if args.engine in {"jadx", "both"}:
        results["engines"]["jadx"] = run_jadx(apk, out_dir / "jadx", deobf=args.deobf, no_res=not args.include_res)
    if args.engine in {"vineflower", "both"}:
        results["engines"]["vineflower"] = run_vineflower(apk, out_dir / "vineflower", args.timeout_seconds)

    if nested_apks and results["engines"].get("jadx", {}).get("java_files", 0) <= 10:
        base = next((Path(p) for p in nested_apks if Path(p).name == "base.apk"), None)
        if base:
            results["base_apk_hint"] = str(base)
            results["base_jadx"] = run_jadx(base, out_dir / "base" / "jadx", deobf=args.deobf, no_res=not args.include_res)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
