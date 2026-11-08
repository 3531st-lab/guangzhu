import guangzhu
from guangzhu.selfcheck import selfcheck


def test_package_import():
    assert guangzhu.__version__ == "0.3.0"


def test_selfcheck_passes():
    result = selfcheck()
    assert result["passed"], result["failures"]
