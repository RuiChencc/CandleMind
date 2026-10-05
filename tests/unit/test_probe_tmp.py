
import os
def test_probe(tmp_path):
    print(f"TMP={tmp_path}")
    print(f"exists={os.path.isdir(str(tmp_path))}")
    print(f"w={os.access(str(tmp_path), os.W_OK)}")
    p = tmp_path / "x.json"
    try:
        p.write_text("{}", encoding="utf-8")
        print("write OK")
    except Exception as e:
        print(f"write FAIL {type(e).__name__}: {e}")
    print(f"tmp parent attrs={os.stat(str(tmp_path.parent)).st_mode}")
