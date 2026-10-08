"""Basic tests for uchr package."""

from uchr import uchr


def test_package_import():
    """Test that the package can be imported."""
    import uchr

    assert uchr is not None


def test_uchr_module_import():
    """Test that the uchr module can be imported."""

    assert uchr is not None


def test_uchr_function_exists():
    """Test that the main uchr function exists."""
    from uchr.uchr import uchr

    assert callable(uchr)
