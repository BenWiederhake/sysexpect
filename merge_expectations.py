#!/usr/bin/env python3

from collections import defaultdict
import argparse
import json
import pathlib
import sys


def update_or_equal(dict_, key, new_value):
    if key in dict_:
        old_value = dict_[key]
        if old_value == new_value:
            return 0
        old_without_mtime = dict(old_value)
        del old_without_mtime["mtime"]
        new_without_mtime = dict(new_value)
        del new_without_mtime["mtime"]
        if old_without_mtime != new_without_mtime:
            print(f"ERROR: CONFLICT for key {key}:\n{old_value}\n{new_value}")
            return 1
        # At this point, the conflict is only about mtime. This is actually quite common, so we want to report it only once, each.
        if old_value["mtime"] is None:
            # Already reported, nothing to do.
            return 0
        print(
            f"Warning: Conflicting mtime for {key} (e.g. {old_value['mtime']} vs. {new_value['mtime']})",
            file=sys.stderr,
        )
        old_value['mtime'] = None
        # No need to update dict_, since it still contains old_value by reference.
    else:
        dict_[key] = new_value
    return 0


def do_merge(sources):
    # Step 1: Resolve potential conflicts and prepare data:
    path_to_filedict = dict()
    path_to_all_children = defaultdict(set)
    # TODO: Stream instead of doing multi-pass.
    # Also, memory-efficiency in general.
    errors = 0
    for source_index, source in enumerate(sources):
        for file_expectation in source:
            # Wtf, black?!
            assert (
                file_expectation["type"] == "file"
            ), f"Entry in source #{i} (0-indexed) does not have type=file. Maybe target and sources mixed up?"
            name = file_expectation["name"]
            path = pathlib.Path(name)
            errors += update_or_equal(path_to_filedict, path.as_posix(), file_expectation)
            if name != ".":
                path_to_all_children[path.parent.as_posix()].add(path.name)

    # Step 2: Generate new expectations
    # Specifically, we now expect that each directory *only* contains the mentioned files.
    for parent, children in path_to_all_children.items():
        assert parent in path_to_filedict
        parent_entry = path_to_filedict[parent]
        assert parent_entry["filetype"] == "dir"
        assert parent_entry["children"] == None
        children_list = list(children)
        children_list.sort()
        parent_entry["children"] = children_list

    # Sanity check that we caught all dirs
    for entry in path_to_filedict.values():
        if entry["filetype"] != "dir":
            continue
        if "children" not in entry:
            print(f"Not checking children of {entry.name}", file=sys.stderr)

    # Step 3: Emit deduplicated, rearranged data
    expectations = list(path_to_filedict.values())
    del path_to_filedict  # Early gc, just in case it helps
    expectations.sort(key=lambda e: e["name"])

    return expectations, errors


def run(args):
    sources = []
    for source_filename in args.source_filenames:
        with open(source_filename, "r") as fp:
            sources.append(json.load(fp))
    result, errors = do_merge(sources)
    with open(args.result_filename, "w") as fp:
        json.dump(result, fp)
    if errors:
        print(f"Encountered {errors} errors. Output file is usable, but will cause false positives.")
        exit(1)


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "result_filename",
        metavar="RESULT.total.json",
    )
    parser.add_argument(
        "source_filenames",
        metavar="TWO_OR_MORE_SOURCES.deb.json",
        nargs="+"
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    if len(args.source_filenames) == 1:
        print(f"Only one source file given. This does not usually make sense, aborting.", file=sys.stderr)
        exit(1)
    run(args)
