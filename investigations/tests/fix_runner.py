#!/usr/bin/env python3
"""Fix run_cinderx_tests.sh to handle signal crashes gracefully.

When test_cinderjit crashes mid-run (SIGBUS, SIGSEGV, SIGABRT), the test
runner sees no 'Ran N tests' line and reports ERROR (did not execute).
This fix:
1. Captures the exit code from timeout
2. Detects signal kills (exit > 128)
3. Counts partial test results from dots output
4. Reports as CRASH instead of ERROR
"""

import sys

SCRIPT = '/home/alexturner/local/cinderx_dev/cinderx/run_cinderx_tests.sh'

with open(SCRIPT, 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]

    # Fix 1: Replace 'OUTPUT=$(timeout ...) || true' with separate exit capture
    if 'OUTPUT=$(timeout 120 python3 -m unittest' in line and '|| true' in line:
        # Remove the '|| true' and add TEST_EXIT capture
        fixed = line.replace(') || true', ')')
        new_lines.append(fixed)
        new_lines.append('    TEST_EXIT=$?\n')
        i += 1
        continue

    # Fix 2: Before the 'else # Genuine error' block, insert crash detection
    if i + 1 < len(lines) and line.strip() == 'else' and 'Genuine error' in lines[i + 1]:
        # Insert crash detection elif before the else
        new_lines.append('        elif [ "$TEST_EXIT" -gt 128 ]; then\n')
        new_lines.append('            # Process killed by signal (segfault, bus error, abort)\n')
        new_lines.append('            SIG_NUM=$((TEST_EXIT - 128))\n')
        new_lines.append('            # Count test dots from partial output before crash\n')
        new_lines.append('            PARTIAL_LINE=$(echo "$OUTPUT" | grep -oE \'^[.EFsSx]+$\' | head -1)\n')
        new_lines.append('            PARTIAL_PASS=$(echo "$PARTIAL_LINE" | tr -cd \'.\' | wc -c)\n')
        new_lines.append('            PARTIAL_ERR=$(echo "$PARTIAL_LINE" | tr -cd \'E\' | wc -c)\n')
        new_lines.append('            PARTIAL_FAIL=$(echo "$PARTIAL_LINE" | tr -cd \'F\' | wc -c)\n')
        new_lines.append('            printf "${RED}CRASH${RESET} (signal %d, ~%d pass, ~%d fail, ~%d error before crash)\\n" "$SIG_NUM" "$PARTIAL_PASS" "$PARTIAL_FAIL" "$PARTIAL_ERR"\n')
        new_lines.append('            FAILED_SUITES+=("$suite")\n')
        new_lines.append('            TOTAL_PASS=$((TOTAL_PASS + PARTIAL_PASS))\n')
        new_lines.append('            TOTAL_FAIL=$((TOTAL_FAIL + PARTIAL_FAIL))\n')
        new_lines.append('            TOTAL_ERROR=$((TOTAL_ERROR + PARTIAL_ERR))\n')
        # Keep the original else
        new_lines.append(line)
        i += 1
        continue

    new_lines.append(line)
    i += 1

with open(SCRIPT, 'w') as f:
    f.writelines(new_lines)

print('Fix applied successfully')
# Verify by checking for key patterns
with open(SCRIPT, 'r') as f:
    content = f.read()
assert 'TEST_EXIT=$?' in content, 'TEST_EXIT capture not found'
assert 'CRASH' in content, 'CRASH handler not found'
assert 'signal' in content, 'signal detection not found'
print('All assertions passed')
