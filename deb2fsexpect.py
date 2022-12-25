#!/usr/bin/env python3

from debian import debfile
import hashlib
import json
import sys
import tarfile


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
    elif info.isdev():
        return "dev"
    raise AssertionError(info.name, info.type)


def extract_info(debfile_object):
    expectations = []
    controlfile = debfile_object.control
    # TODO: Do something with controlfile.scripts?
    scripts = controlfile.scripts()
    if scripts:
        print(f"ignoring {len(scripts)} scripts: {scripts}")
    datatarfile = debfile_object.data.tgz()
    # Using the datatarfile as an iterator *might* interfere with the functions "getmembers'.
    for info_member in datatarfile:
        if info_member.isreg():
            sha256_hasher = hashlib.sha256()
            info_content_fp = datatarfile.extractfile(info_member)
            assert info_content_fp is not None, info_member
            sha256_hasher.update(info_content_fp.read())
            member_sha256 = sha256_hasher.hexdigest()
        else:
            member_sha256 = ""
        new_expectation = {
            "type": "file",
            "filetype": tarinfo_type_to_string(info_member),
            "name": info_member.name,
            "size": info_member.size,
            "mtime": info_member.mtime,
            "mode": info_member.mode,
            "linkname": info_member.linkname,
            "uid": info_member.uid,
            "gid": info_member.gid,
            "uname": info_member.uname,
            "gname": info_member.gname,
            "pax_headers": info_member.pax_headers,
            # FIXME: device maj min?
            # FIXME: link target?
            # FIXME: LNK inode identity?
            "sha256": member_sha256,
        }
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
