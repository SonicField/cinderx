"""B2 GDB test: repeated exception path calls."""
from cinderx.jit import force_compile

def f(d, k):
    try:
        return d[k]
    except KeyError:
        return -1

force_compile(f)

# Call with miss multiple times
for i in range(100):
    r = f({}, "x")

print("survived 100 calls, result:", r)
