"""
test_load_attr_module_inline — Correctness tests for LOAD_ATTR_MODULE inline
dict access specialisation.

Targets: The LOAD_ATTR_MODULE inline fast path replaces the IC-based
LoadModuleAttrCached approach with direct dict entry access:
1. GuardType receiver is PyModule_Type
2. Load md_dict -> ma_keys -> dk_version
3. Compare dk_version against CPython IC cached version
4. Guard on version match
5. Call JITRT_LoadModuleDictEntry(keys, index) for direct entry access
6. CheckField on result (deopt if NULL = deleted attr)

This bypasses the IC entirely for a direct memory path. The guard depends on
dk_version being invalidated whenever the dict contents change. CPython
guarantees this: dk_version is incremented on any mutation (insert, delete,
update) and on dict resize.

These tests verify that JIT-compiled code produces IDENTICAL results to the
interpreter when module attributes are accessed, mutated, deleted, or when
the dict is resized. Each test compares JIT output against a known reference.
"""

import types
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def make_test_module(name, **attrs):
    """Create a fresh module with given attributes."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestLoadAttrModuleInline(unittest.TestCase):

    # ── Test 1: Basic correctness — access module attr under JIT ──────

    def test_basic_module_attr_access(self):
        """Basic correctness — math.pi and math.e under JIT."""
        import math

        def get_pi():
            return math.pi

        def get_e():
            return math.e

        cinderjit.force_compile(get_pi)
        cinderjit.force_compile(get_e)

        self.assertEqual(get_pi(), math.pi)
        self.assertEqual(get_e(), math.e)

    # ── Test 2: Module attribute mutation — change value after JIT ─────

    def test_mutation_after_jit(self):
        """Module attribute mutation after JIT compilation."""
        test_mod = make_test_module("test_mod", value=42, label="original")

        def get_value(mod):
            return mod.value

        cinderjit.force_compile(get_value)

        # Verify original value
        self.assertEqual(get_value(test_mod), 42)

        # Mutate the module attribute (dk_version should change)
        test_mod.value = 99

        # JIT-compiled function should see the new value (guard fires, deopts)
        self.assertEqual(get_value(test_mod), 99)

    # ── Test 3: Module attribute deletion — del attr after JIT ────────

    def test_deletion_after_jit(self):
        """Module attribute deletion after JIT compilation."""
        del_mod = make_test_module("del_mod", target=100, keep=200)

        def get_target(mod):
            return mod.target

        def get_keep(mod):
            return mod.keep

        cinderjit.force_compile(get_target)
        cinderjit.force_compile(get_keep)

        # Delete the target attribute
        del del_mod.target

        # Access should raise AttributeError (CheckField should deopt, then
        # interpreter raises the error)
        with self.assertRaises(AttributeError):
            get_target(del_mod)

        # Other attributes should still work
        self.assertEqual(get_keep(del_mod), 200)

    # ── Test 4: Dict resize — add many attributes to force resize ─────

    def test_dict_resize(self):
        """Dict resize — force ma_keys reallocation."""
        resize_mod = make_test_module("resize_mod", original=42)

        def get_original(mod):
            return mod.original

        cinderjit.force_compile(get_original)

        # Verify pre-resize
        self.assertEqual(get_original(resize_mod), 42)

        # Add many attributes to force dict resize (CPython dicts resize at
        # 2/3 capacity; initial capacity is 8, so adding ~10 attributes should
        # trigger at least one resize)
        for i in range(50):
            setattr(resize_mod, f"padding_{i}", i)

        # Original attribute should still be accessible (guard fires on
        # dk_version change, deopts to interpreter which re-does the lookup)
        self.assertEqual(get_original(resize_mod), 42)

    # ── Test 5: Multiple mutations — rapid attribute changes ──────────

    def test_rapid_mutations(self):
        """Rapid attribute mutations (1000 cycles)."""
        rapid_mod = make_test_module("rapid_mod", counter=0)

        def get_counter(mod):
            return mod.counter

        cinderjit.force_compile(get_counter)

        for i in range(1000):
            rapid_mod.counter = i
            self.assertEqual(get_counter(rapid_mod), i)

    # ── Test 6: New attribute added after JIT compilation ─────────────

    def test_new_attr_after_jit(self):
        """Access newly added attribute after JIT compilation."""
        new_attr_mod = make_test_module("new_attr_mod", existing=10)

        def get_new_attr(mod):
            return mod.new_attr

        # Verify it raises AttributeError before the attr exists
        with self.assertRaises(AttributeError):
            get_new_attr(new_attr_mod)

        # Now add the attribute
        new_attr_mod.new_attr = 777

        cinderjit.force_compile(get_new_attr)

        self.assertEqual(get_new_attr(new_attr_mod), 777)

    # ── Test 7: Module replacement — different module same function ────

    def test_different_modules_same_function(self):
        """Different modules through same function."""
        mod_a = make_test_module("mod_a", shared=100)
        mod_b = make_test_module("mod_b", shared=200)

        def get_shared(mod):
            return mod.shared

        cinderjit.force_compile(get_shared)

        self.assertEqual(get_shared(mod_a), 100)
        self.assertEqual(get_shared(mod_b), 200)

    # ── Test 8: Attribute type change ─────────────────────────────────

    def test_attribute_type_change(self):
        """Attribute value type change (int -> str -> list)."""
        type_mod = make_test_module("type_mod", val=42)

        def get_val(mod):
            return mod.val

        cinderjit.force_compile(get_val)

        # Change type: int -> str
        type_mod.val = "hello"
        self.assertEqual(get_val(type_mod), "hello")

        # Change type: str -> list
        type_mod.val = [1, 2, 3]
        self.assertEqual(get_val(type_mod), [1, 2, 3])

    # ── Test 9: Stability — repeated access under JIT (no mutation) ───

    def test_stability_repeated_access(self):
        """Stability — 10000 accesses to os.sep under JIT."""
        import os

        def get_sep():
            return os.sep

        cinderjit.force_compile(get_sep)

        ref_sep = os.sep
        for _ in range(10000):
            self.assertEqual(get_sep(), ref_sep)


if __name__ == "__main__":
    unittest.main()
