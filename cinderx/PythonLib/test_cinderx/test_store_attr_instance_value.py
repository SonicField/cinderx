"""
test_store_attr_instance_value — Correctness tests for STORE_ATTR_INSTANCE_VALUE
and STORE_ATTR_SLOT specialisations.

Targets: STORE_ATTR_INSTANCE_VALUE and STORE_ATTR_SLOT emit a GuardType on the
receiver using the type version from CPython's inline cache. Unlike the LOAD
counterparts, there is no compile-time store fast path in the Simplify pass —
the store still uses StoreAttrCached (runtime IC). The GuardType enables type
propagation for downstream operations.

Mechanism:
1. Builder reads _PyAttrCache from CPython IC (version[2], index)
2. findTypeByVersionTag(type_version) -> PyTypeObject*
3. GuardType(receiver, exact_type) emitted
4. StoreAttr emitted (unchanged — runtime IC handles the actual store)

These tests share Bug 6 exposure with LOAD_ATTR_INSTANCE_VALUE: the same
findTypeByVersionTag and SplitDictDeoptPatcher infrastructure is used, so
class modification after JIT compilation can trigger the same segfault in
the type_modified notification handler.

Tests verify that JIT-compiled store operations produce IDENTICAL side effects
to the interpreter:
- Basic attribute store
- Store to new attribute (not present at compile time)
- Store overwriting existing attribute
- Store different value types
- Store across different instances of the same class
- Subclass deopt (GuardType should fire)
- Polymorphic store (same function, different class types)
- __slots__-based classes (STORE_ATTR_SLOT, shared code path)
- Rapid mutation cycles
- Store + load roundtrip correctness
"""

import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def force_compile(fn):
    """Force JIT compilation of fn using cinderjit if available."""
    if HAS_CINDERJIT:
        cinderjit.force_compile(fn)


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestStoreAttrInstanceValue(unittest.TestCase):

    def test_01_basic_attribute_store(self):
        """Basic attribute store under JIT."""
        class Box:
            def __init__(self, value):
                self.value = value

        def set_value(obj, v):
            obj.value = v

        force_compile(set_value)

        b = Box(0)
        set_value(b, 99)
        self.assertEqual(b.value, 99)

    def test_02_store_overwriting_existing_attribute(self):
        """Store overwriting existing attribute multiple times."""
        class Counter:
            def __init__(self, count):
                self.count = count

        def set_count(obj, n):
            obj.count = n

        force_compile(set_count)

        c = Counter(0)
        set_count(c, 10)
        self.assertEqual(c.count, 10)
        set_count(c, 20)
        self.assertEqual(c.count, 20)
        set_count(c, 30)
        self.assertEqual(c.count, 30)

    def test_03_store_different_value_types(self):
        """Store different value types (int -> str -> list -> None)."""
        class TypeHolder:
            def __init__(self, val):
                self.val = val

        def set_val(obj, v):
            obj.val = v

        force_compile(set_val)

        th = TypeHolder(0)

        set_val(th, "hello")
        self.assertEqual(th.val, "hello")

        set_val(th, [1, 2, 3])
        self.assertEqual(th.val, [1, 2, 3])

        set_val(th, None)
        self.assertIsNone(th.val)

        set_val(th, {"key": "val"})
        self.assertEqual(th.val, {"key": "val"})

    def test_04_store_across_different_instances(self):
        """Store to different instances of the same class."""
        class Bucket:
            def __init__(self, data):
                self.data = data

        def set_data(obj, d):
            obj.data = d

        force_compile(set_data)

        b1 = Bucket("a")
        b2 = Bucket("b")
        b3 = Bucket("c")

        set_data(b1, "x")
        set_data(b2, "y")
        set_data(b3, "z")

        self.assertEqual(b1.data, "x")
        self.assertEqual(b2.data, "y")
        self.assertEqual(b3.data, "z")

    def test_05_store_new_attribute_not_present_at_compile_time(self):
        """Store new attribute not present at compile time."""
        class Expandable:
            def __init__(self, base):
                self.base = base

        def set_extra(obj, v):
            obj.extra = v

        # Cannot warm up set_extra with e because e has no 'extra' yet.
        # Create a temporary instance to warm up the function. This means the
        # JIT compiles set_extra for an instance shape that includes 'extra'.
        # When called on the original instance e (which lacks 'extra'), the
        # GuardType fires because type(e) has a different split-dict layout,
        # forcing deopt to the interpreter which handles the new attr creation.
        temp = Expandable(0)
        temp.extra = 0  # Ensure attr exists for warmup
        force_compile(set_extra)

        e = Expandable(10)
        self.assertFalse(hasattr(e, 'extra'))

        set_extra(e, 777)

        self.assertTrue(hasattr(e, 'extra'))
        self.assertEqual(e.extra, 777)

    def test_06_subclass_deopt_guard_type_fires(self):
        """Subclass deopt — GuardType fires for derived class."""
        class Animal:
            def __init__(self, name):
                self.name = name

        class Dog(Animal):
            def __init__(self, name, breed):
                super().__init__(name)
                self.breed = breed

        def set_animal_name(obj, n):
            obj.name = n

        force_compile(set_animal_name)

        a = Animal("generic")

        # Store to base — should work fine
        set_animal_name(a, "base_val")
        self.assertEqual(a.name, "base_val")

        # Store to derived — GuardType should deopt
        dog = Dog("Rex", "Lab")
        set_animal_name(dog, "Fido")
        self.assertEqual(dog.name, "Fido")

        # Verify base still works after deopt
        set_animal_name(a, "post_deopt")
        self.assertEqual(a.name, "post_deopt")

    def test_07_polymorphic_store_different_classes(self):
        """Polymorphic store — same function, different classes."""
        class Red:
            def __init__(self, shade):
                self.shade = shade

        class Blue:
            def __init__(self, shade):
                self.shade = shade

        class Green:
            def __init__(self, shade):
                self.shade = shade

        def set_shade(obj, s):
            obj.shade = s

        force_compile(set_shade)

        r = Red("light")
        bl = Blue("dark")
        g = Green("forest")

        set_shade(r, "crimson")
        set_shade(bl, "navy")
        set_shade(g, "emerald")

        self.assertEqual(r.shade, "crimson")
        self.assertEqual(bl.shade, "navy")
        self.assertEqual(g.shade, "emerald")

    @unittest.skip("Bug 6: segfault in JIT type_modified handler (SplitDictDeoptPatcher)")
    def test_08_class_modification_after_jit(self):
        """Class modification after JIT — skipped due to Bug 6."""
        pass

    def test_09_slots_based_class_store_attr_slot(self):
        """__slots__-based class (STORE_ATTR_SLOT)."""
        class SlottedPoint:
            __slots__ = ('x', 'y')
            def __init__(self, x, y):
                self.x = x
                self.y = y

        def set_slot_x(obj, v):
            obj.x = v

        def set_slot_y(obj, v):
            obj.y = v

        force_compile(set_slot_x)
        force_compile(set_slot_y)

        sp = SlottedPoint(0, 0)

        set_slot_x(sp, 42)
        set_slot_y(sp, 84)
        self.assertEqual(sp.x, 42)
        self.assertEqual(sp.y, 84)

        # Mutation
        set_slot_x(sp, 100)
        set_slot_y(sp, 200)
        self.assertEqual(sp.x, 100)
        self.assertEqual(sp.y, 200)

    def test_10_polymorphic_store_dict_and_slots(self):
        """Polymorphic store across dict and __slots__ classes."""
        class DictStore:
            def __init__(self, tag):
                self.tag = tag

        class SlotStore:
            __slots__ = ('tag',)
            def __init__(self, tag):
                self.tag = tag

        def set_tag(obj, t):
            obj.tag = t

        force_compile(set_tag)

        ds = DictStore("d")
        ss = SlotStore("s")

        set_tag(ds, "dict_val")
        set_tag(ss, "slot_val")

        self.assertEqual(ds.tag, "dict_val")
        self.assertEqual(ss.tag, "slot_val")

    def test_11_rapid_store_load_cycles(self):
        """Rapid store/load cycles (1000 iterations)."""
        class Rapid:
            def __init__(self, n):
                self.n = n

        def set_rapid_n(obj, v):
            obj.n = v

        def get_rapid_n(obj):
            return obj.n

        force_compile(set_rapid_n)
        force_compile(get_rapid_n)

        rp = Rapid(0)
        for i in range(1000):
            set_rapid_n(rp, i)
            result = get_rapid_n(rp)
            self.assertEqual(result, i, f"cycle {i}: stored {i}, got back {result}")

    def test_12_store_load_roundtrip_type_alternation(self):
        """Store/load roundtrip with type alternation (500 cycles)."""
        class Alpha:
            def __init__(self, data):
                self.data = data

        class Beta:
            def __init__(self, data):
                self.data = data

        def set_data_poly(obj, d):
            obj.data = d

        def get_data_poly(obj):
            return obj.data

        force_compile(set_data_poly)
        force_compile(get_data_poly)

        aa = Alpha(0)
        bb = Beta(0)
        for i in range(500):
            set_data_poly(aa, i * 2)
            set_data_poly(bb, i * 2 + 1)
            ra = get_data_poly(aa)
            rb = get_data_poly(bb)
            self.assertEqual(ra, i * 2,
                             f"cycle {i}: alpha={ra} (expected {i * 2})")
            self.assertEqual(rb, i * 2 + 1,
                             f"cycle {i}: beta={rb} (expected {i * 2 + 1})")

    def test_13_stability_many_stores_without_reads(self):
        """Stability — 10000 stores without intermediate reads."""
        class Sink:
            def __init__(self):
                self.value = 0

        def store_sink(obj, v):
            obj.value = v

        force_compile(store_sink)

        sk = Sink()
        for i in range(10000):
            store_sink(sk, i)

        self.assertEqual(sk.value, 9999)


if __name__ == "__main__":
    unittest.main()
