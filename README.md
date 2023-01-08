# sysexpect

Proof of Concept: This program analyzes your entire system, and reports any and all additions/modifications/deletions when compared with the stock data from the packet manager. In other words, it checks the "expectation" that all system files are exactly as they should be from the package manager, unmodified, without any additional or missing files.

Because I'm still exploring:
- All of this is very Debian-centric for now.
- Don't mind the code quality. If it reliably works or reports an error (instead of producing corrupt data), it's good enough.
- Usability is terrible, because I don't know what parts will be actually necessary.
- Entirely unoptimized python. That said, processing the `.deb`s is done in-memory instead of unpacking everything and spamming your disk.
- The git history isn't very legible, but each snapshot should still be reasonably useful.

## Why not just md5sums?

- MD5 is insecure, and can be easily broken. Why rely on it if there's a better alternative, SHA256? That's what this PoC uses.
- There are many more attributes: File type, non-regular files (sockets, symlinks, hardlinks(!)), permissions, file ownership
- This PoC also checks for additional files, which cannot be easily detected by an md5sums-like approach.
- Finally, apt sets the mtime of files upon installation. This PoC also checks for deviations of file mtimes, as this indicates some kind of irregularity that might be interesting.

## Usage

You need to install the Debian-native package `python3-debian` (which should be installed through apt, not pip/PyPI).

Installing `python3-xattr` is optional, but without it the extended attributes of files cannot be checked.

1. Collect one or more `.deb`s that you expect to be installed on your system. You can use `dpkg-query` and your local system cache for a first approximation:
   `LC_ALL=C apt list --installed | grep -Ev '^Listing...' | sed -Ee 's,^([^/]+)/[^ ]+ ([^ ]+) ([^ ]+) \[.+,/var/cache/apt/archives/\1_\2_\3.deb,' -e 's,:,%3a,' | xargs cp -t /tmp/expected_debs/`
   Note that all the packages will be missing that are installed but no longer cached for some reason.
   Also note that the output of `apt list` is unstable.
2. Convert each `.deb` to a list of expectations: `./deb2fsexpect.py FOO.deb FOO.deb.json`
   If your `.deb`s are in `/tmp/expected_debs/`, you could use:
   `for deb in /tmp/expected_debs/*.deb; do echo "Processing $deb ..."; ./deb2fsexpect.py --expect-run-merged --expect-usr-merged $deb $deb.json; done`
   Alternatively, you could also do this in parallel:
   `parallel -j15 -i ./deb2fsexpect.py --expect-run-merged --expect-usr-merged '{}' '{}.json' -- /tmp/expected_debs/*.deb`
3. OPTIONAL: If you have multiple `.deb`s *AND* you want a report of all the unexpected/new files, use `./merge_expectations.py RESULT.total.json TWO_OR_MORE_SOURCES.deb.json` to merge the JSON files from the previous step. Using the above running example, this would be:
   `./merge_expectations.py /tmp/expected_debs/total.json /tmp/expected_debs/*.deb.json`
4. Check that the currently running system satisfies all expectations: `./check_expect.py FOO.json`
   If you want to check the expectations against a mounted system, just pass `--destdir /path/to/mnt-or-destdir/` as the first argument.
   Here's how an invocation can look like:
   `sudo ./check_expect.py --ignore-mtime --ignore-pycache --ignore-children-of-dir /var/cache/apt/archives --ignore-children-of-dir /var/lib/apt/lists --ignore-children-of-dir /var/log /tmp/expected_debs/total.json`

Note that this may take up a lot of memory, so you may want to run this in a `ulimit -m` shell, if you're worried about OOM. For reference, the JSON files generated in step 2 are in total 136 MiB on my system.

To get a rough overview over the types of findings, you can do this:
```
$ cat output_from_check_expect.txt | jq 'keys | .[]' | sort | uniq -c | sort -n
      1 "linkname"
      3 "xattr_base64"
     12 "uid"
     25 "gid"
     28 "sha256"
     28 "size"
     41 "mode"
    289 "extraneous_children"
    361 "name"
```

## TODO

- We currently mis-detect generated files and other things that would be handled by `{pre,post}rm` scripts.
- In fact, we ignore all 'preinst', 'postinst', 'prerm', 'postrm', and 'config' scripts. At least a warning is generated saying so.
- `check_expect.py` can probably be sped up significantly by doing something in parallel.
- Parse preinst/postinst scripts to detect calls to dpkg-divert and update-alternatives. This is doomed to fail, since shell scripts are by design Turing complete.
- `/var/lib/dpkg/info/`: This directory contains all control files of all installed or configured packages, I think. Therefore, `deb2fsexpect.py` could issue expectations
- `deb2fsexpect.py` does not really read the control tar, therefore it also ignores the list of `conffiles`, and raises warnings if the installed file is different than the package maintainer's version.
- uid/gid/mode: It seems that the preinst/postinst/etc scripts may also change the owner of a file, which is reasonable, as a static tarfile cannot possibly know the numeric ID of system groups of the target system. However, this means that these things are set dynamically as part of scripts, which again raises the issue of parsing shell scripts. The same happens with permissions, although I don't really understand why this is necessary in the first place.
- The shell scripts are also where extended attributes are set. On my system, that affects three files: /bin/ping (cap_net_raw) and /usr/lib/{x86_64,i386}-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-ptp-helper (cap_net_bind_service and cap_net_admin).

In short, the biggest thing missing is a shell script interpreter.

## Further Notes

### Duplicate files

Sadly, some deb packages contain the same file at the same path. This wastes some disk space and bandwidth during updates, but it's no cause of worry.

### Duplicate files with different mtimes

```
Warning: Conflicting mtime for usr/share/doc/libexif12/changelog.Debian.gz (e.g. 1663552334 vs. 1663571684)
Warning: Conflicting mtime for usr/share/locale/be/LC_MESSAGES/libexif-12.mo (e.g. 1663552334 vs. 1663571684)
Warning: Conflicting mtime for etc/pulse/client.conf (e.g. 1665905116 vs. 1665891704)
```

This is probably a symptom of non-reproducibility: I guess that the mtime in the .deb package is just the time at which the package was built, instead of being derived only from the package source.

It's not a cause of worry, and handled gracefully here: While merging, any such case results in the `mtime` field being set to `null`, indicating that there is no expectation regarding the mtime of the system file.

### Duplicate files with different contents

```
ERROR: CONFLICT for key usr/bin/pg_config:
{'type': 'file', 'filetype': 'reg', 'name': './usr/bin/pg_config', 'size': 6393, 'mtime': 1667901552, 'mode': 493, 'linkname': None, 'uid': 0, 'gid': 0, 'pax_headers': {}, 'sha256': '19fffe64afa5a626f3e5a257cfa9c9ec8fa3f272295c74e2cfce460557dac830', 'dev_inode': None, 'children': None}
{'type': 'file', 'filetype': 'reg', 'name': './usr/bin/pg_config', 'size': 1229, 'mtime': 1597408163, 'mode': 493, 'linkname': None, 'uid': 0, 'gid': 0, 'pax_headers': {}, 'sha256': '56e697a2dd537bcaf15258f5aa10fa39b4506e7a9866fd466731ba21d0d2a2f7', 'dev_inode': None, 'children': None}
```

This means that more than one package attempts to install a file at that path, and those files are not identical. In this case, it tries to make `/usr/bin/pg_config` a 1229 byte shell script *and* a 6393 byte perl script.

As far as I can see, this happens at least for the following files:

```
/lib/ld-linux.so.2: libc6:i386, libc6-i386
/usr/bin/pg_config: postgresql-common, libpq-dev
```

The main reason for this "conflict" is that we don't parse dpkg-divert calls yet.
Why are these dynamic? This should be part of the control data!
Anyway, parsing these is doomed to fail. You can inspect the list of active diversions on your system: `cat /var/lib/dpkg/diversions`

The same happens with calls to update-alternative.

### Dynamic caches

Some packages install 0-byte files and populate them using precomputed data during install time. Most prominently, the aspell dictionaries do that.
