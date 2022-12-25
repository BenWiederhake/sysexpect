#!/usr/bin/env python3

from collections import defaultdict
import json
import pathlib
import sys


def update_or_equal(dict_, key, value):
    if key in dict_:
        assert dict_[key] == value
    else:
        dict_[key] = value


def do_merge(sources):
    # Step 1: Resolve potential conflicts and prepare data:
    path_to_filedict = dict()
    path_to_all_children = defaultdict(set)
    # TODO: Stream instead of doing multi-pass.
    # Also, memory-efficiency in general.
    for source_index, source in enumerate(sources):
        for file_expectation in source:
            # Wtf, black?!
            assert (
                file_expectation["type"] == "file"
            ), f"Entry in source #{i} (0-indexed) does not have type=file. Maybe target and sources mixed up?"
            name = file_expectation["name"]
            path = pathlib.Path(name)
            update_or_equal(path_to_filedict, path.as_posix(), file_expectation)
            path_to_all_children[path.parent.as_posix()].add(path.name)

    # Step 2: Emit deduplicated data
    expectations = list(path_to_filedict.values())
    del path_to_filedict  # Early gc, just in case it helps
    expectations.sort(key=lambda e: e["name"])

    # Step 3: Emit the new expectations
    # Specifically, we now expect that each directory *only* contains the mentioned files.
    for parent, children in path_to_all_children.items():
        children_list = list(children)
        children_list.sort()
        expectations.append(
            {
                "type": "listdir",
                "name": "./" + parent,  # Damn you, pathlib!
                "children": children_list,
            }
        )

    return expectations


def run(result_filename, source_filenames):
    sources = []
    for source_filename in source_filenames:
        with open(source_filename, "r") as fp:
            sources.append(json.load(fp))
    result = do_merge(sources)
    with open(result_filename, "w") as fp:
        json.dump(result, fp)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            f"USAGE: {sys.argv[0]} RESULT.total.json TWO_OR_MORE_SOURCES.deb.json",
            file=sys.stderr,
        )
        exit(1)
    else:
        run(sys.argv[1], sys.argv[2:])
