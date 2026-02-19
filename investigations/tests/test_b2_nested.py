"""Test B2 nested try/except — does Return(nullptr) skip outer handlers?"""
import sys
import cinderjit

def nested_try(d, k):
    """Inner except ValueError, outer except KeyError."""
    try:
        try:
            return d[k]
        except ValueError:
            return "value_error"
    except KeyError:
        return "key_error"

cinderjit.force_compile(nested_try)

# This should return "key_error" (outer handler catches)
# If Return(nullptr) is used on no-match, the outer handler is skipped.
try:
    r = nested_try({}, "missing")
    if r == "key_error":
        print("NESTED PASS: outer handler caught KeyError, r =", r)
    else:
        print("NESTED FAIL: expected key_error, got", r)
except KeyError:
    print("NESTED FAIL: KeyError propagated to caller — outer handler skipped!")
except Exception as e:
    print(f"NESTED FAIL: unexpected {type(e).__name__}: {e}")

# Also test: no-match with no outer handler (should propagate cleanly)
def single_try(d, k):
    try:
        return d[k]
    except ValueError:
        return "value_error"

cinderjit.force_compile(single_try)

try:
    single_try({}, "missing")
    print("SINGLE FAIL: should have raised")
except KeyError:
    pass

exc = sys.exc_info()
if exc == (None, None, None):
    print("SINGLE PASS: exc_info cleared after catch")
else:
    print("SINGLE FAIL: exc_info leaked:", exc)

# Test: simple match still works
def simple_match(d, k):
    try:
        return d[k]
    except KeyError:
        return -1

cinderjit.force_compile(simple_match)
r = simple_match({}, "x")
assert r == -1, f"Expected -1, got {r}"
print("SIMPLE PASS: match works, r =", r)

print("\n=== All nested tests done ===")
