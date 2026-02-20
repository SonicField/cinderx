"""Tests for speculative method inlining (tiered compilation with IC feedback).

Falsifiers for the speculative inlining pipeline:
- Step 2: IC warmup and persistence across calls
- Step 3+4: Type change triggers deopt with correct results
- Step 4: Cold function with no IC data does not crash
"""
import unittest

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
class TestSpeculativeInlining(unittest.TestCase):

    def test_ic_warmup_monomorphic(self):
        """Step 2: IC accumulates type data for monomorphic call sites."""
        class MyClass:
            def method(self):
                return 42

        def caller():
            obj = MyClass()
            return obj.method()

        cinderjit.force_compile(caller)
        # Call enough times to trigger tier1 threshold (N1=1000)
        for _ in range(1200):
            result = caller()
            self.assertEqual(result, 42)

    def test_type_change_deopt_correctness(self):
        """Steps 3+4: Type change after monomorphic warmup produces correct result."""
        class Dog:
            def speak(self):
                return "woof"

        class Cat:
            def speak(self):
                return "meow"

        animals = [Dog()]

        def polymorphic_caller():
            return animals[0].speak()

        cinderjit.force_compile(polymorphic_caller)

        # Warm with Dog (monomorphic)
        for _ in range(1200):
            self.assertEqual(polymorphic_caller(), "woof")

        # Switch to Cat — deopt should fire, correct result
        animals[0] = Cat()
        self.assertEqual(polymorphic_caller(), "meow")

    def test_cold_function_no_crash(self):
        """Step 4: force_compile on never-called function does not crash."""
        class Bird:
            def speak(self):
                return "tweet"

        def cold_caller():
            b = Bird()
            return b.speak()

        cinderjit.force_compile(cold_caller)
        self.assertEqual(cold_caller(), "tweet")

    def test_multiple_method_calls(self):
        """Multiple method calls in one function all work correctly."""
        class Point:
            __slots__ = ("x", "y")
            def __init__(self, x, y):
                self.x = x
                self.y = y
            def magnitude(self):
                return (self.x**2 + self.y**2) ** 0.5

        def multi_method():
            p1 = Point(3.0, 4.0)
            p2 = Point(5.0, 12.0)
            return p1.magnitude() + p2.magnitude()

        cinderjit.force_compile(multi_method)
        for _ in range(1200):
            result = multi_method()
            self.assertAlmostEqual(result, 18.0, places=5)

    def test_polymorphic_site_no_crash(self):
        """Polymorphic call sites (multiple types) do not crash."""
        class A:
            def method(self):
                return 1
        class B:
            def method(self):
                return 2

        objects = [A(), B()]

        def poly_caller():
            total = 0
            for obj in objects:
                total += obj.method()
            return total

        cinderjit.force_compile(poly_caller)
        for _ in range(1200):
            self.assertEqual(poly_caller(), 3)


    def test_type_reswitch_correctness(self):
        """Type switch Dog->Cat->Dog produces correct results throughout."""
        class Dog:
            def speak(self):
                return "woof"
        class Cat:
            def speak(self):
                return "meow"

        animals = [Dog()]
        def switcher():
            return animals[0].speak()

        cinderjit.force_compile(switcher)
        for _ in range(1200):
            self.assertEqual(switcher(), "woof")
        animals[0] = Cat()
        self.assertEqual(switcher(), "meow")
        animals[0] = Dog()
        self.assertEqual(switcher(), "woof")

    def test_inheritance_no_override(self):
        """Subclass without method override uses parent method correctly."""
        class Base:
            def method(self):
                return "base"
        class Sub(Base):
            pass  # No override

        def caller():
            obj = Sub()
            return obj.method()

        cinderjit.force_compile(caller)
        for _ in range(1200):
            self.assertEqual(caller(), "base")


if __name__ == "__main__":
    unittest.main()
