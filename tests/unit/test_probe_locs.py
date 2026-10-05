import os
def test_write_locations(tmp_path):
    print('')
    targets = {
        "project_root": r"D:/OpenCode/projects/PA_Agent/probe_pytest_root.txt",
        "pytest_tmp_dir": r"D:/OpenCode/projects/PA_Agent/.pytest_tmp/probe_direct.txt",
        "tmp_path_child": str(tmp_path / "probe_child.txt"),
        "system_temp": os.path.join(os.environ.get("TEMP", r"C:/Windows/Temp"), "probe_dsh.txt"),
        "dsh_temp": r"D:/OpenCode/temp/probe_pytest_dsh.txt",
    }
    for tag, p in targets.items():
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("ok")
            print(f"{tag}: OK")
        except Exception as e:
            print(f"{tag}: FAIL {type(e).__name__}: {e}")
    print(f"tmp_path={tmp_path} w={os.access(str(tmp_path), os.W_OK)}")