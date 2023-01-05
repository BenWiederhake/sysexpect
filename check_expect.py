#!/usr/bin/env python3.11

from debian import debfile
import argparse
import hashlib
import json
import os
import sys

try:
    import xattr

    CAN_CHECK_XATTR = True
except ModuleNotFoundError:
    CAN_CHECK_XATTR = False
    # TODO: Try using pyxattr instead. It's basically the same thing.
    print(
        f"Warning: Module 'xattr' not installed. Note that this is different from the 'pyxattr' module.",
        file=sys.stderr,
    )

if getattr(hashlib, "file_digest", None) is None:
    print(
        f"Sorry, this program needs Python 3.11, for hashlib.file_digest. This seems to be running {sys.version}",
        file=sys.stderr,
    )
    exit(2)


# Taken from my /usr/include/x86_64-linux-gnu/sys/stat.h
S_IFMT   = 0o170000
S_IFDIR  = 0o040000
S_IFCHR  = 0o020000
S_IFBLK  = 0o060000
S_IFREG  = 0o100000
S_IFIFO  = 0o010000
S_IFLNK  = 0o120000
S_IFSOCK = 0o140000

# Taken from https://pubs.opengroup.org/onlinepubs/9699919799/
S_ISUID = 0o4000
S_ISGID = 0o2000
S_ISVTX = 0o1000
S_IRUSR = 0o400
S_IWUSR = 0o200
S_IXUSR = 0o100
S_IRGRP = 0o040
S_IWGRP = 0o020
S_IXGRP = 0o010
S_IROTH = 0o004
S_IWOTH = 0o002
S_IXOTH = 0o001

MAX_MTIME_DIFF = 2


def simplify_mode(stat_mode):
    fmt_bits = stat_mode & S_IFMT
    access_bits = stat_mode & ~S_IFMT
    if fmt_bits == S_IFREG:
        return "reg", access_bits
    if fmt_bits == S_IFDIR:
        return "dir", access_bits
    if fmt_bits == S_IFLNK:
        return "sym", access_bits
    if fmt_bits == S_IFCHR:
        return "chr", access_bits
    if fmt_bits == S_IFBLK:
        return "blk", access_bits
    if fmt_bits == S_IFIFO:
        return "fifo", access_bits
    if fmt_bits == S_IFSOCK:
        # TODO: Never generated by tars?!
        return "sock", access_bits
    raise AssertionError(
        f"weird access bits {fmt_bits} (0o{fmt_bits:o}) (access_bits = 0o{access_bits:o})"
    )


def check_for_conflict(report, key, actual, expected):
    if actual == expected or expected is None:
        # All is well!
        return False
    report[key] = {"expected": expected, "actual": actual}
    return True


def fetch_actual_xattr_dict(filename):
    return dict(xattr.xattr(filename, xattr.XATTR_NOFOLLOW))


def check_expectation(args, expectation):
    assert expectation["type"] == "file", f"Can't handle type {expectation['type']}"
    effective_path = args.destdir + expectation["name"]
    report = dict(name=expectation["name"])
    # TODO: if stat.st_nlink > 1, cache it somehow for easier hardlink checks
    has_any_conflict = False
    try:
        stat_result = os.stat(effective_path, follow_symlinks=False)
    except FileNotFoundError:
        report["error_stat"] = "FileNotFoundError"
        return report
    except PermissionError:
        report["error_stat"] = "PermissionError during stat (try running as root)"
        return report
    actual_filetype, actual_mode = simplify_mode(stat_result.st_mode)
    expected_filetype = expectation["filetype"]
    if expected_filetype == "lnk":
        # It may be a hardlink, but stat will report the same filetype as the linked-to file, naturally.
        # Ironically, this may be any filetype, including directories, symlinks, etc.
        # However, anything except a regular file would be weird.
        expected_filetype = "reg"
    has_any_conflict |= check_for_conflict(
        report, "filetype", actual_filetype, expected_filetype
    )
    has_any_conflict |= check_for_conflict(
        report, "mode", actual_mode, expectation["mode"]
    )
    # TODO: Save (st_dev, st_ino) to identify hardlinks later
    # TODO: Use st_nlink to speed up hardlink detection
    has_any_conflict |= check_for_conflict(
        report, "uid", stat_result.st_uid, expectation["uid"]
    )
    has_any_conflict |= check_for_conflict(
        report, "gid", stat_result.st_gid, expectation["gid"]
    )
    if actual_filetype == "reg":
        has_any_conflict |= check_for_conflict(
            report, "size", stat_result.st_size, expectation["size"]
        )
    if actual_filetype == "reg":
        try:
            with open(effective_path, "rb") as fp:
                actual_sha256 = hashlib.file_digest(fp, "sha256").hexdigest()
        except PermissionError:
            report["error_read"] = "PermissionError during read (try running as root)"
            has_any_conflict = True
            actual_sha256 = None
        if actual_sha256 is not None:
            has_any_conflict |= check_for_conflict(
                report, "sha256", actual_sha256, expectation["sha256"]
            )
    if actual_filetype == "dir" and expectation["filetype"] == "dir" and expectation["children"] is not None:
        try:
            actual_children = os.listdir(effective_path)
        except PermissionError:
            actual_children = []
            report["error_listdir"] = "PermissionError during listdir (try running as root)"
            has_any_conflict = True
        # Any missing children will be reported through their respective expectation entry.
        # Therefore, only report extraneous children here:
        actual_children = set(actual_children)
        actual_children.difference_update(expectation["children"])
        extraneous_children = list(actual_children)
        extraneous_children.sort()
        if extraneous_children:
            has_any_conflict = True
            report['extraneous_children'] = extraneous_children
    if expectation["dev_inode"] is not None:
        actual_dev_inode = (os.major(stat_result.st_dev), os.minor(stat_result.st_dev))
        has_any_conflict |= check_for_conflict(
            report, "dev_inode", actual_dev_inode, expectation["dev_inode"]
        )
    if expectation["mtime"] is not None and actual_filetype != "dir":
        mtime_diff = abs(expectation["mtime"] - stat_result.st_mtime)
        if mtime_diff > MAX_MTIME_DIFF:
            has_any_conflict = True
            report["mtime"] = {
                "actual": stat_result.st_mtime,
                "expected": expectation["mtime"],
            }
    if expectation["linkname"] is not None:
        if expectation["filetype"] == "sym":
            if actual_filetype == "sym":
                actual_destination = os.readlink(effective_path)
                has_any_conflict |= check_for_conflict(
                    report, "linkname", actual_destination, expectation["linkname"]
                )
            else:
                report["symlink"] = "Uncheckable; actual is not a symlink"
                assert has_any_conflict
        elif expectation["filetype"] == "lnk":
            try:
                stat_other = os.stat(args.destdir + expectation["linkname"], follow_symlinks=False)
            except:
                has_any_conflict = True
                report["error_stat_link_dest"] = "PermissionError during stat (try running as root)"
            else:
                this_ident = (stat_result.st_dev, stat_result.st_ino)
                other_ident = (stat_other.st_dev, stat_other.st_ino)
                if this_ident != other_ident:
                    has_any_conflict = True
                    report["hardlink"] = {"this_file": this_ident, "expected": other_ident}
        else:
            raise AssertionError(
                f"non-linking filetype {expectation['filetype']} tries to link to {expectation['linkname']}?!"
            )
    if CAN_CHECK_XATTR:
        try:
            actual_xattr = fetch_actual_xattr_dict(effective_path)
        except PermissionError:
            has_any_conflict = True
            report["error_xattr"] = "PermissionError during xattr (try running as root)"
        else:
            expected_xattr = expectation["pax_headers"]
            has_any_conflict |= check_for_conflict(
                report, "xattr", actual_xattr, expected_xattr
            )

    if has_any_conflict:
        return report
    assert len(report) == 1, report
    return None


def run_expectations(args, expectations):
    if not args.destdir.endswith("/"):
        args.destdir += "/"
    reports = []
    for expectation in expectations:
        report = check_expectation(args, expectation)
        if report is not None:
            reports.append(report)
            print(report)
    return reports


def run(args):
    with open(args.json_filename, "r") as fp:
        expectations = json.load(fp)
    _reports = run_expectations(args, expectations)
    # TODO: Do something more reasonable with the reports?


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "json_filename",
        metavar="total_or_deb.json",
    )
    parser.add_argument(
        "--destdir",
        default="/",
        help="Root of the filesystem under test. (default: '/')",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run(args)
