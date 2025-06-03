from collections import defaultdict
import itertools
import os

from typing import Optional, TypedDict

class Failure(TypedDict):
    test: str
    path: str
    kind: str
    variant: Optional[str]
    mq_system: str

failures: list[Failure] = []

class Run(TypedDict):
    test: str
    mq_system: str

all_runs: list[Run] = []

for root, dirs, files in os.walk("2025"):
    for file in files:
        if "HW Run" in root or "HW Run" in file:
            if ".txt" in file:
                fpath = os.path.join(root, file)
                with open(fpath) as f:
                    contents = f.read()

                if "##[error]The operation was canceled." in contents:
                    continue

                by_group = contents.split("##[group]")
                for group in by_group:
                    if "---------[ start test" not in group:
                        continue

                    _, system_str = group.split("+++ mq.sh sem -info ", maxsplit=1)
                    mq_system, _ = system_str.split("\x1b", maxsplit=1)

                    assert group.count("-----------[ end test ") == 1
                    # ignore anything after end test
                    group, test_str = group.split("-----------[ end test ")
                    test, _ = test_str.split(" ]-----------")

                    all_runs.append({
                        "test": test,
                        "mq_system": mq_system,
                    })

                    if "FAILED" in group or "command failed, aborting" in group:

                        kind = None
                        variant = None

                        if "seL4 failed assertion" in group:
                            if "NODE_STATE(ksCurTime) < MAX_RELEASE_TIME" in group:
                                kind = "seL4 assertion"
                                variant = "release time"
                            else:
                                # this is an assert because it's kind of important
                                raise Exception("unknown kind of seL4 assertion encountered")

                        if "Boot failure detected" in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "boot failure"
                            variant = "detected"

                        if "</testsuite>" in group and "Error parsing parsed_results.xml" in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "IDK, weird testsuite failure"

                        if "</testsuite>" in group and "*** FAILURES DETECTED ***" in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "tests failed"

                        if "Unable to ssh to tftp.keg.cse.unsw.edu.au" in group and "Lock acquired, we are allowed to run" not in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "ssh failure"

                        if "Connection closed by UNKNOWN port 65535" in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "ssh failure"

                        if "[-- Console server shutting down --]" in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "console server rebooted"

                        if "console: Unable to connect to 10.13.1.202:3109" in group:
                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            kind = "console server dead"

                        if "[[Timeout]]" in group:
                            if kind == "boot failure":
                                # is this right?
                                print(test, fpath)
                                continue

                            assert kind is None, f"previous: {kind} in {test} {fpath}"
                            assert group.count("[[Timeout]]") == 1

                            if "</testcase>" in group:
                                kind = "output timeout"
                                variant = "during tests"

                            elif "Booting Linux on physical CPU" in group or "[    0.000000] Linux version" in group:
                                kind = "boot failure"
                                variant = "undetected (booted linux)"

                            else:
                                pre_timeout_msg, _ = group.split("[[Timeout]]")
                                # look at last 5 lines
                                pre_timeout_lines = pre_timeout_msg.split("\n")[-6:]
                                pre_timeout_lines_str = "\n".join(pre_timeout_lines)
                                if "Jumping to kernel-image entry point" in pre_timeout_lines_str:
                                    kind = "output timeout"
                                    variant = "after jumping to kernel"
                                elif "Enabling MMU and paging" in pre_timeout_lines_str:
                                    kind = "output timeout"
                                    variant = "after enabling mmu"
                                elif "clock_sync_test[1]" in pre_timeout_lines_str:
                                    kind = "output timeout"
                                    variant = "after clock sync test"
                                elif "Bootstrapping kernel" in pre_timeout_lines_str:
                                    kind = "output timeout"
                                    variant = "after bootstrap kernel"
                                elif "reserved virt address space regions" in pre_timeout_lines_str:
                                    kind = "output timeout"
                                    variant = "after printing addr space regions"
                                elif "ZynqMP>" in pre_timeout_lines_str:
                                    kind = "boot failure"
                                    variant = "undetected (zynqmp console)"
                                elif "u-boot=>" in pre_timeout_lines_str:
                                    kind = "boot failure"
                                    variant = "undetected (uboot console)"

                        if kind is None:
                            print()
                            print(test)
                            print(fpath)
                            print("\n".join(group.splitlines()[-30:]))
                        else:
                            failures.append({
                                "test": test,
                                "path": fpath,
                                "kind": kind,
                                "variant": variant,
                                "mq_system": mq_system,
                            })
                    else:
                        assert "Test summary" in group, group

failures = sorted(failures, key=lambda c: (c["kind"], c["variant"], c["test"]))
all_runs = sorted(all_runs, key=lambda c: (c["test"], c["mq_system"]))

failure_counts = defaultdict(int)

with open("failures.txt", "w") as f:
    for case in failures:
        print(case["test"], file=f)
        print("\tpath:", case["path"], file=f)
        print("\tsystem:", case["mq_system"], file=f)
        print("\tkind:", case['kind'], file=f)
        if case["variant"]:
            print("\tvariant:", case["variant"], file=f)

        failure_counts[(case["test"], case["mq_system"])] += 1

print("Output to failures.txt")

with open("all_runs.txt", "w") as f:
    for test, cases in itertools.groupby(all_runs, key=lambda r: r["test"]):
        print(test, file=f)
        for system, cases in itertools.groupby(cases, key=lambda r: r["mq_system"]):
            print("\tsystem: {}, count={}".format(system, len(list(cases))), file=f, end="")
            failure_count = failure_counts[(test, system)]
            if failure_count != 0:
                print(", failures={}".format(failure_count), file=f)
            else:
                print(file=f)

print("Output to all_runs.txt")
