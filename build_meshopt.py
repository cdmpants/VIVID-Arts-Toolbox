"""Build meshoptimizer as a shared library for VIVID Arts Toolbox.

Usage:
    python build_meshopt.py <path_to_meshoptimizer_source>

Example:
    python build_meshopt.py ../meshoptimizer

The meshoptimizer source is available at:
    https://github.com/zeux/meshoptimizer

Outputs vivid_arts_toolbox/lib/meshoptimizer.dll
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def find_compiler():
    if shutil.which("cl"):
        return "msvc"
    if shutil.which("clang++"):
        return "clang"
    if shutil.which("g++"):
        return "gcc"
    return None


def build_msvc(src_dir, output_path):
    obj_dir = output_path.parent
    cmd = [
        "cl", "/O2", "/DNDEBUG", "/LD", "/EHsc",
        "/DMESHOPTIMIZER_API=__declspec(dllexport)",
        f"/Fe:{output_path}",
        f"/Fo:{obj_dir}\\",
        str(src_dir / "simplifier.cpp"),
        f"/I{src_dir}",
    ]
    subprocess.run(cmd, check=True)
    # Clean up MSVC artifacts
    for ext in (".obj", ".lib", ".exp"):
        p = obj_dir / f"meshoptimizer{ext}"
        if p.exists():
            p.unlink()


def build_gcc_clang(compiler, src_dir, output_path):
    export_macro = "__declspec(dllexport)" if sys.platform == "win32" else '__attribute__((visibility("default")))'
    cmd = [
        compiler, "-O2", "-shared", "-std=c++11", "-o", str(output_path),
        f"-DMESHOPTIMIZER_API={export_macro}",
        f"-I{src_dir}",
        str(src_dir / "simplifier.cpp"),
    ]
    subprocess.run(cmd, check=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    meshopt_root = Path(sys.argv[1]).resolve()
    src_dir = meshopt_root / "src"

    if not (src_dir / "meshoptimizer.h").exists():
        print(f"Error: meshoptimizer.h not found in {src_dir}")
        print("Pass the root meshoptimizer directory (containing src/).")
        sys.exit(1)

    output_dir = Path(__file__).parent / "vivid_arts_toolbox" / "lib"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "meshoptimizer.dll"

    compiler = find_compiler()
    if not compiler:
        print("No C++ compiler found. Install Visual Studio Build Tools, clang, or g++.")
        sys.exit(1)

    print(f"Compiler: {compiler}")
    print(f"Source:   {src_dir}")
    print(f"Output:   {output_path}")

    if compiler == "msvc":
        build_msvc(src_dir, output_path)
    else:
        exe = "clang++" if compiler == "clang" else "g++"
        build_gcc_clang(exe, src_dir, output_path)

    print(f"Done — {output_path}")


if __name__ == "__main__":
    main()
