"""Regression test: self identity through diamond CFG under auto-compile.

Tests that speculative dispatch diamond CFGs (CondBranchCheckType +
fast/slow paths + merge) do not corrupt the 'self' register through
register allocation overlap.
"""
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


class Animal:
    def __init__(self, name, sound):
        self.name = name
        self.sound = sound

    def speak(self):
        n = self.name
        s = self.sound
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


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestDiamondSelfIdentity(unittest.TestCase):

    def setUp(self):
        cinderjit.auto()

    def test_polymorphic_dispatch(self):
        animals = [Dog(), Cat(), Bird(), Dog(), Cat()]
        for iters in [10, 50, 100, 500, 1000]:
            for _ in range(iters):
                for animal in animals:
                    result = animal.speak()
                    self.assertIsInstance(result, str)

    def test_type_identity_after_warmup(self):
        animals = [Dog(), Cat(), Bird()]
        for _ in range(1200):
            for a in animals:
                a.speak()
        for a in animals:
            result = a.speak()
            self.assertIsInstance(result, str)
            self.assertIn("says", result)


if __name__ == '__main__':
    unittest.main()
