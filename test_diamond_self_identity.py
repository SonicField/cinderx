#!/usr/bin/env python3
"""Regression test: self identity through diamond CFG under auto-compile.

Tests that speculative dispatch diamond CFGs (CondBranchCheckType +
fast/slow paths + merge) do not corrupt the 'self' register through
register allocation overlap.

The bug: the register allocator assigns the Phi result (from the
diamond merge) to the same physical register as self (LoadArg<0>).
When the diamond writes to result, it overwrites self. This manifests
as AttributeError when self becomes a wrong type.

This test creates a polymorphic dispatch pattern similar to Richards:
multiple types with different attributes call the same method. Under
auto-compile, the JIT compiles with type specialization. If the diamond
CFG corrupts self, the wrong type's attributes are accessed.

Usage:
    PYTHONJIT=1 python3.12 test_diamond_self_identity.py
"""
import sys
import os

# Add PythonLib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, "cinderx", "PythonLib"))


class Animal:
    """Base class — polymorphic dispatch target."""
    def __init__(self, name, sound):
        self.name = name
        self.sound = sound

    def speak(self):
        # Multiple attribute accesses on self — creates multiple
        # diamond CFGs when speculative dispatch is active.
        n = self.name
        s = self.sound
        # Verify self is still the correct type after diamond CFGs
        assert isinstance(self, Animal), (
            f"self corrupted: expected Animal, got {type(self).__name__}"
        )
        return f"{n} says {s}"


class Dog(Animal):
    def __init__(self):
        super().__init__("Rex", "woof")
        self.tricks = 3

    def speak(self):
        n = self.name
        s = self.sound
        t = self.tricks
        assert isinstance(self, Dog), (
            f"self corrupted: expected Dog, got {type(self).__name__}"
        )
        return f"{n} says {s} (knows {t} tricks)"


class Cat(Animal):
    def __init__(self):
        super().__init__("Whiskers", "meow")
        self.lives = 9

    def speak(self):
        n = self.name
        s = self.sound
        v = self.lives
        assert isinstance(self, Cat), (
            f"self corrupted: expected Cat, got {type(self).__name__}"
        )
        return f"{n} says {s} ({v} lives left)"


class Bird(Animal):
    def __init__(self):
        super().__init__("Tweety", "tweet")
        self.can_fly = True

    def speak(self):
        n = self.name
        s = self.sound
        f = self.can_fly
        assert isinstance(self, Bird), (
            f"self corrupted: expected Bird, got {type(self).__name__}"
        )
        return f"{n} says {s} (flies: {f})"


def polymorphic_dispatch(animals, iterations):
    """Call speak() on different types — polymorphic call site."""
    for _ in range(iterations):
        for animal in animals:
            result = animal.speak()
            # Verify the result is a string (not None or wrong value)
            assert isinstance(result, str), (
                f"speak() returned {type(result).__name__}, expected str"
            )


def test_diamond_self_identity():
    """Test self identity through diamond CFGs under auto-compile."""
    try:
        import cinderjit
        cinderjit.auto()
    except ImportError:
        print("SKIP: cinderjit not available")
        return True

    animals = [Dog(), Cat(), Bird(), Dog(), Cat()]

    # Increasing iterations to trigger compilation + recompilation
    for iters in [10, 50, 100, 500, 1000]:
        try:
            polymorphic_dispatch(animals, iters)
            print(f"PASS: polymorphic_dispatch({iters})")
        except AssertionError as e:
            print(f"FAIL: polymorphic_dispatch({iters}) — {e}")
            return False
        except AttributeError as e:
            print(f"FAIL: polymorphic_dispatch({iters}) — {e}")
            print("  self identity corrupted through diamond CFG")
            return False
        except Exception as e:
            print(f"FAIL: polymorphic_dispatch({iters}) — {type(e).__name__}: {e}")
            return False

    print("PASS: all diamond self-identity checks passed")
    return True


def test_richards_self_identity():
    """Test richards benchmark self identity under auto-compile."""
    try:
        import cinderjit
        cinderjit.auto()
    except ImportError:
        print("SKIP: cinderjit not available")
        return True

    sys.path.insert(0, os.path.join(script_dir, "cinderx", "benchmarks"))
    from richards import Richards

    r = Richards()
    # Test at iterations below the pre-existing SIGBUS threshold (~5000)
    for iters in [10, 50, 100, 500]:
        try:
            result = r.run(iters)
            if not result:
                print(f"FAIL: richards({iters}) returned False")
                return False
            print(f"PASS: richards({iters})")
        except AttributeError as e:
            print(f"FAIL: richards({iters}) — {e}")
            print("  self identity likely corrupted through diamond CFG")
            return False
        except Exception as e:
            print(f"FAIL: richards({iters}) — {type(e).__name__}: {e}")
            return False

    print("PASS: all richards self-identity checks passed")
    return True


if __name__ == "__main__":
    passed = True

    print("=== Diamond CFG self-identity regression tests ===")
    print()

    print("--- polymorphic dispatch (synthetic) ---")
    if not test_diamond_self_identity():
        passed = False
    print()

    print("--- richards (real workload) ---")
    if not test_richards_self_identity():
        passed = False
    print()

    if passed:
        print("ALL PASSED")
        sys.exit(0)
    else:
        print("FAILURES DETECTED")
        sys.exit(1)
