import compileall
import pathlib
import re


def test_python_files_compile() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    exclude = re.compile(r"(/|\\)(__pycache__|\.venv|venv|\.git|node_modules)(/|\\)")

    src_ok = compileall.compile_dir(str(root / "src"), quiet=1, rx=exclude)
    run_ok = compileall.compile_file(str(root / "run_bot.py"), quiet=1)

    assert src_ok and run_ok, "Обнаружены ошибки синтаксиса в Python-файлах."
