#!/usr/bin/env python3
"""Regression test for speculative dispatch under auto-compile.

Tests that the GuardType speculative expansion produces correct results
when auto-compile is active and polymorphic dispatch occurs. This
specifically targets the builder.cpp approach's interaction with
auto-compile recompilation.

The crash pattern: richards_full works with force_compile but crashes
at 1000+ iterations with auto-compile. The bug manifests as
AttributeError ('_RPacket object has no attribute packetPending')
indicating wrong type flowing through speculative dispatch paths.

Usage:
  PYTHONJIT=1 python3.12 test_autocompile_regression.py
"""
import sys
import os

# Add PythonLib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
pythonlib = os.path.join(script_dir, "cinderx", "PythonLib")
sys.path.insert(0, pythonlib)

def test_richards_autocompile():
    """Richards benchmark under auto-compile with increasing iterations.

    Tests at multiple iteration counts to catch bugs that only manifest
    after recompilation thresholds are crossed.
    """
    try:
        import cinderjit
        cinderjit.auto()
    except ImportError:
        print("SKIP: cinderjit not available")
        return True

    sys.path.insert(0, os.path.join(script_dir, "cinderx", "benchmarks"))
    from richards import Richards

    r = Richards()

    # Increasing iteration counts to trigger auto-compile recompilation
    for iters in [10, 100, 500, 1000, 5000]:
        try:
            result = r.run(iters)
            if not result:
                print(f"FAIL: richards({iters}) returned False (incorrect result)")
                return False
            print(f"PASS: richards({iters})")
        except AttributeError as e:
            print(f"FAIL: richards({iters}) — {e}")
            print("  This indicates wrong type flowing through speculative dispatch.")
            return False
        except Exception as e:
            print(f"FAIL: richards({iters}) — {type(e).__name__}: {e}")
            return False

    print("PASS: all richards auto-compile iterations correct")
    return True


def test_nn_module_autocompile():
    """nn_module benchmark under auto-compile."""
    try:
        import cinderjit
        cinderjit.auto()
    except ImportError:
        print("SKIP: cinderjit not available")
        return True

    sys.path.insert(0, os.path.join(script_dir, "cinderx", "benchmarks"))
    try:
        from nn_module import bench_nn_module
    except ImportError:
        print("SKIP: nn_module benchmark not available")
        return True

    for iters in [100, 1000, 5000, 50000]:
        try:
            bench_nn_module(iters)
            print(f"PASS: nn_module({iters})")
        except Exception as e:
            print(f"FAIL: nn_module({iters}) — {type(e).__name__}: {e}")
            return False

    print("PASS: all nn_module auto-compile iterations correct")
    return True


if __name__ == "__main__":
    passed = True

    print("=== Auto-compile regression tests ===")
    print()

    print("--- richards (polymorphic dispatch) ---")
    if not test_richards_autocompile():
        passed = False
    print()

    print("--- nn_module (attribute access) ---")
    if not test_nn_module_autocompile():
        passed = False
    print()

    if passed:
        print("ALL PASSED")
        sys.exit(0)
    else:
        print("FAILURES DETECTED")
        sys.exit(1)
