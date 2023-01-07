#!/usr/bin/env python3.11

from debian import debfile
import argparse
import hashlib
import json
import sys
import tarfile


if getattr(hashlib, "file_digest", None) is None:
    print(
        f"Sorry, this program needs Python 3.11, for hashlib.file_digest. This seems to be running {sys.version}",
        file=sys.stderr,
    )
    exit(2)


def tarinfo_type_to_string(info):
    if info.isreg():
        return "reg"
    elif info.isdir():
        return "dir"
    elif info.issym():
        return "sym"
    elif info.islnk():
        return "lnk"
    elif info.ischr():
        return "chr"
    elif info.isblk():
        return "blk"
    elif info.isfifo():
        return "fifo"
    raise AssertionError(info.name, info.type)


def extract_info(debfile_object):
    expectations = []
    controlfile = debfile_object.control
    # TODO: Do something with controlfile.scripts?
    # TODO: Parse scripts for calls to dpkg-divert
    # TODO: Parse scripts for calls to update-alternatives
    # Note that sometimes these are hidden in other scripts from other packages. Aaaah!
    # TODO: Parse 'conffiles' and mark them as dontcare for sha256/mtime/size.
    scripts = controlfile.scripts()
    if scripts:
        print(f"ignoring {len(scripts)} scripts: {scripts.keys()}")
    datatarfile = debfile_object.data.tgz()
    # Using the datatarfile as an iterator *might* interfere with the functions "getmembers'.
    for info_member in datatarfile:
        if info_member.isreg():
            info_content_fp = datatarfile.extractfile(info_member)
            assert info_content_fp is not None, info_member
            member_sha256 = hashlib.file_digest(info_content_fp, "sha256").hexdigest()
        else:
            member_sha256 = None
        if info_member.isdev():
            dev_inode = (info_member.devmajor, info_member.devminor)
        else:
            dev_inode = None
        new_expectation = {
            "type": "file",
            "filetype": tarinfo_type_to_string(info_member),
            "name": info_member.name,
            "size": info_member.size,
            # The mtime of directories has no real weight, discard it:
            "mtime": None if info_member.isdir() else info_member.mtime,
            "mode": info_member.mode,
            "linkname": info_member.linkname if info_member.linkname else None,  # Both symlinks and hardlinks!
            "uid": info_member.uid,
            "gid": info_member.gid,
            # "uname": info_member.uname,  # Can't really use it, changes from system to system anyway.
            # "gname": info_member.gname,  # Can't really use it, changes from system to system anyway.
            "pax_headers": info_member.pax_headers,
            "sha256": member_sha256,
            "dev_inode": dev_inode,
            "children": None,
        }
        if info_member.pax_headers:
            print(
                f"Warning: Non-empty PAX-headers for file {info_member.name}: {info_member.pax_headers}",
                file=sys.stderr,
            )
        expectations.append(new_expectation)

    return expectations


def run(args):
    debfile_object = debfile.DebFile(args.deb_filename)
    expectations = extract_info(debfile_object)
    with open(args.json_filename, "w") as fp:
        json.dump(expectations, fp)


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "deb_filename",
        metavar="some/path/to/package.deb",
    )
    parser.add_argument(
        "json_filename",
        metavar="other/path/to/output.json",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run(args)
