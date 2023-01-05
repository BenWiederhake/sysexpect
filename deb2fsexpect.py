#!/usr/bin/env python3.11

from debian import debfile
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
            "mtime": info_member.mtime,
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


def run(deb_filename, json_filename):
    debfile_object = debfile.DebFile(deb_filename)
    expectations = extract_info(debfile_object)
    with open(json_filename, "w") as fp:
        json.dump(expectations, fp)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            f"USAGE: {sys.argv[0]} some/path/to/package.deb other/path/to/output.json",
            file=sys.stderr,
        )
        exit(1)
    else:
        run(sys.argv[1], sys.argv[2])
